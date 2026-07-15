import os
import uuid
import hashlib
from pypdf import PdfReader
from docx import Document
from qdrant_client import QdrantClient
# Сюда добавлены новые компоненты для быстрой проверки дубликатов
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

def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def extract_text_from_docx(file_path):
    doc = Document(file_path)
    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text)
    return "\n".join(text)

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
            # Быстро спрашиваем у Qdrant, знает ли он уже этот файл
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

            # Если файла в базе нет, начинаем его читать и нарезать
            if file_name.lower().endswith('.pdf'):
                file_text = extract_text_from_pdf(file_path)
            elif file_name.lower().endswith('.docx'):
                file_text = extract_text_from_docx(file_path)
            else:
                continue

            if not file_text.strip():
                print(f" ⚠️ Пропущен (пустой текст): {file_name}")
                continue

            chunks = chunk_text(file_text)
            print(f"   🔥 Новый файл! Нарезаем на {len(chunks)} кусков и генерируем векторы...")
            
            for i, chunk in enumerate(chunks):
                text_for_vector = f"passage: {chunk}"
                vector = list(encoder.embed([text_for_vector]))[0].tolist()

                hash_object = hashlib.md5(f"{file_path}_{i}".encode('utf-8'))
                deterministic_uuid = str(uuid.UUID(hash_object.hexdigest()))

                point = PointStruct(
                    id=deterministic_uuid,
                    vector=vector,
                    payload={"text": chunk, "source": file_name}
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