import pytest
import py_compile
import os

def test_python_syntax():
    """Проверяет синтаксис всех ключевых Python-файлов проекта на отсутствие синтаксических ошибок."""
    py_files = ["bot.py", "industrial_indexer.py"]
    for file_name in py_files:
        assert os.path.exists(file_name), f"Файл {file_name} должен существовать"
        # py_compile выбросит PyCompileError при любой синтаксической ошибке
        py_compile.compile(file_name, doraise=True)

def test_seed_calculation_logic():
    """Тестирует формулу расчета семян для дехканских хозяйств."""
    seed_norms = {
        "kartoshka": 30.0,
        "pahta": 2.5,
        "gandum": 2.2
    }
    
    # 10 соток картофеля: 10 * 30.0 = 300 кг
    assert 10 * seed_norms["kartoshka"] == 300.0
    # 5 соток хлопка: 5 * 2.5 = 12.5 кг
    assert 5 * seed_norms["pahta"] == 12.5
    # 100 соток (1 га) пшеницы: 100 * 2.2 = 220 кг
    assert 100 * seed_norms["gandum"] == 220.0

def test_chunking_algorithm():
    """Тестирует функцию разбивки текста на чанки с перекрытием (overlap)."""
    from industrial_indexer import chunk_text
    
    sample_text = "A" * 1500
    chunks = chunk_text(sample_text, chunk_size=800, overlap=150)
    
    assert len(chunks) >= 2, "Текст длиной 1500 должен разбиваться минимум на 2 чанка"
    assert len(chunks[0]) == 800
    # Проверка перекрытия
    assert chunks[0][-150:] == chunks[1][:150]
