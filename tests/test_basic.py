import sys
import os
import pytest
import py_compile

# Гарантируем, что корневая папка проекта всегда доступна для импорта в тестах
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def test_python_syntax():
    """Проверяет синтаксис всех ключевых Python-файлов проекта."""
    py_files = [os.path.join(ROOT_DIR, "bot.py"), os.path.join(ROOT_DIR, "industrial_indexer.py")]
    for file_path in py_files:
        assert os.path.exists(file_path), f"Файл {file_path} должен существовать"
        py_compile.compile(file_path, doraise=True)

def test_seed_calculation_logic():
    """Тестирует формулу расчета семян для дехканских хозяйств."""
    seed_norms = {
        "kartoshka": 30.0,
        "pahta": 2.5,
        "gandum": 2.2
    }
    
    # 10 соток картофеля: 10 * 30.0 = 300 кг
    assert 10 * seed_norms["kartoshka"] == pytest.approx(300.0)
    # 5 соток хлопка: 5 * 2.5 = 12.5 кг
    assert 5 * seed_norms["pahta"] == pytest.approx(12.5)
    # 100 соток (1 га) пшеницы: 100 * 2.2 = 220 кг (с учетом погрешности float)
    assert 100 * seed_norms["gandum"] == pytest.approx(220.0)

def test_chunking_algorithm():
    """Тестирует функцию разбивки текста на чанки с перекрытием (overlap)."""
    from industrial_indexer import chunk_text
    
    sample_text = "A" * 1500
    chunks = chunk_text(sample_text, chunk_size=800, overlap=150)
    
    assert len(chunks) >= 2, "Текст длиной 1500 должен разбиваться минимум на 2 чанка"
    assert len(chunks[0]) == 800
    # Проверка перекрытия: конец первого чанка совпадает с началом второго
    assert chunks[0][-150:] == chunks[1][:150]
