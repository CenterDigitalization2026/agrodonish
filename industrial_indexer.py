import os
import uuid
import hashlib
from pypdf import PdfReader
from docx import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from fastembed import TextEmbedding

# ==========================================
# КОНФИГУРАЦИЯ СИСТЕМЫ
# ==========================================
PDF_DIR = "./big_knowledge_base"
COLLECTION_NAME = "agro_large_db"
VECTOR_SIZE = 1024  
BATCH_SIZE = 100  # Отправляем порциями по 100 векторов

print("Запуск ИИ-модели эмбеддингов (E5 Large)...")
encoder = TextEmbedding(model_name="intfloat/multilingual-e5-large")

print("Подключение к серверу Qdrant...")
qdrant_client = QdrantClient(url="http://localhost:6333")

# ==========================================
# ИНИЦИАЛИЗАЦИЯ КОЛЛЕКЦИИ
# ==========================================
try:
    qdrant_client.get_collection(COLLECTION_NAME)
    print(f"ℹ️ Коллекция '{COLLECTION_NAME}' готова. Режим умного добавления данных включен.")
except Exception:
    print(f"✨ Создание НОВОЙ промышленной коллекции '{COLLECTION_NAME}'...")
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE, on_disk=True)
    )

def chunk_text(text, chunk_size=800, overlap=150):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

# --- УМНОЕ ИЗВЛЕЧЕНИЕ СТРАНИЦ ИЗ PDF ---
def extract_chunks_with_metadata_pdf(file_path):
    """
    Постранично читает PDF и нарезает текст каждой страницы отдельно, 
    сохраняя реальный номер страницы.
    """
    reader = PdfReader(file_path)
    chunks_with_meta = []
    
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()
        if page_text and page_text.strip():
            # Нарезаем текст этой конкретной страницы
            page_chunks = chunk_text(page_text, chunk_size=800, overlap=150)
            for chunk in page_chunks:
                chunks_with_meta.append({
                    "text": chunk,
                    "page": page_num
                })
    return chunks_with_meta

# --- ИЗВЛЕЧЕНИЕ ИЗ DOCX (У Word нет четких физических страниц) ---
def extract_chunks_with_metadata_docx(file_path):
    """
    Читает DOCX файл и нарезает на чанки. Номер страницы выставляется как None.
    """
    doc = Document(file_path)
    text_list = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_list.append(para.text)
    full_text = "\n".join(text_list)
    chunks = chunk_text(full_text)
    return [{"text": chunk, "page": None} for chunk in chunks]

def main():
    if not os.path.exists(PDF_DIR):
        print(f"❌ Ошибка: Папка {PDF_DIR} не найдена!")
        return

    # Находим все файлы во всех подпапках
    all_files = []
    for root, dirs, files in os.walk(PDF_DIR):
        for file in files:
            if file.lower().endswith(('.pdf', '.docx')):
                full_path = os.path.join(root, file)
                all_files.append((file, full_path))

    if not all_files:
        print(f"❌ В папке {PDF_DIR} и её подпапках нет подходящих файлов (.pdf или .docx)!")
        return

    print(f"📚 Найдено файлов для анализа (включая подпапки): {len(all_files)}")
    
    points_batch = []
    total_indexed_chunks = 0

    for file_index, (file_name, file_path) in enumerate(all_files, start=1):
        print(f"[{file_index}/{len(all_files)}] Проверка: {file_path}...")
        
        try:
            # === СУПЕР-УМНЫЙ ПРОПУСК СТАРЫХ ФАЙЛОВ ===
            already_indexed, _ = qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source", match=MatchValue(value=file_name))]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False
            )
            
            if already_indexed:
                print(f"   ⏩ Этот файл уже есть в базе знаний. Мгновенно пропускаем.")
                continue
            # =========================================

            # === УМНОЕ ОПРЕДЕЛЕНИЕ АВТОРА И НАЗВАНИЯ КНИГИ ===
            filename_without_ext = os.path.splitext(file_name)[0]
            author = "Вазорати кишоварзии ҶТ"  # Дефолтный автор
            book = filename_without_ext         # Дефолтное название книги

            # Вариант 1: Если файл назван в формате "Автор - Название книги.pdf"
            if " - " in filename_without_ext:
                parts = filename_without_ext.split(" - ", 1)
                author = parts[0].strip()
                book = parts[1].strip()
            else:
                # Вариант 2: Если файл лежит в подпапке (например: big_knowledge_base/А. Салимов/Пчеловодство.pdf)
                rel_path = os.path.relpath(file_path, PDF_DIR)
                path_parts = rel_path.split(os.sep)
                if len(path_parts) >= 2:
                    author = path_parts[0].strip()  # Имя папки становится Автором
                    book = filename_without_ext

            # === ЧТЕНИЕ И НАРЕЗКА С СОХРАНЕНИЕМ СТРАНИЦ ===
            if file_name.lower().endswith('.pdf'):
                chunks_data = extract_chunks_with_metadata_pdf(file_path)
            elif file_name.lower().endswith('.docx'):
                chunks_data = extract_chunks_with_metadata_docx(file_path)
            else:
                continue

            if not chunks_data:
                print(f" ⚠️ Пропущен (пустой текст): {file_name}")
                continue

            print(f"   🔥 Новый файл! Нарезаем на {len(chunks_data)} кусков и генерируем векторы...")
            
            for i, chunk_info in enumerate(chunks_data):
                chunk_text_content = chunk_info["text"]
                page_num = chunk_info["page"]

                text_for_vector = f"passage: {chunk_text_content}"
                vector = list(encoder.embed([text_for_vector]))[0].tolist()

                hash_object = hashlib.md5(f"{file_path}_{i}".encode('utf-8'))
                deterministic_uuid = str(uuid.UUID(hash_object.hexdigest()))

                # Формируем расширенный payload для Qdrant
                payload = {
                    "text": chunk_text_content,
                    "source": file_name,
                    "book": book,
                    "author": author,
                    "page": page_num
                }

                point = PointStruct(
                    id=deterministic_uuid,
                    vector=vector,
                    payload=payload
                )
                points_batch.append(point)

                if len(points_batch) >= BATCH_SIZE:
                    qdrant_client.upload_points(collection_name=COLLECTION_NAME, points=points_batch)
                    total_indexed_chunks += len(points_batch)
                    print(f"   🚀 Отправлена порция векторов в Qdrant. Всего добавлено: {total_indexed_chunks}")
                    points_batch = []

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {file_name}: {e}")

    if points_batch:
        qdrant_client.upload_points(collection_name=COLLECTION_NAME, points=points_batch)
        total_indexed_chunks += len(points_batch)
        print(f"   🚀 Отправлены финальные остатки векторов.")

    print(f"\n🎉 Процесс завершен! Новые данные успешно слились с базой.")

if __name__ == "__main__":
    main()