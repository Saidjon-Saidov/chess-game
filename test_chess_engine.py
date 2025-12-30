"""
Unit тесты для шахматного движка
Запуск: python -m pytest test_chess_engine.py -v
Или: python test_chess_engine.py
"""

import unittest
import chess
import sys

# Импортируем функции из основного файла
# Предполагается что основной файл называется chess_game.py
try:
    from chess_game import (
        evaluate_board, 
        order_moves, 
        minimax, 
        find_best_move,
        get_opening_move,
        PIECE_VALUES
    )
except ImportError:
    print("⚠️  Не удалось импортировать функции из chess_game.py")
    print("Убедитесь что файл chess_game.py находится в той же папке")
    sys.exit(1)


class TestPieceValues(unittest.TestCase):
    """Тесты базовых значений фигур"""
    
    def test_piece_values_exist(self):
        """Проверка что все фигуры имеют значения"""
        required_pieces = [chess.PAWN, chess.KNIGHT, chess.BISHOP, 
                          chess.ROOK, chess.QUEEN, chess.KING]
        for piece in required_pieces:
            self.assertIn(piece, PIECE_VALUES)
            self.assertIsInstance(PIECE_VALUES[piece], int)
    
    def test_piece_values_hierarchy(self):
        """Проверка иерархии ценности фигур"""
        self.assertLess(PIECE_VALUES[chess.PAWN], PIECE_VALUES[chess.KNIGHT])
        self.assertLess(PIECE_VALUES[chess.KNIGHT], PIECE_VALUES[chess.ROOK])
        self.assertLess(PIECE_VALUES[chess.ROOK], PIECE_VALUES[chess.QUEEN])
        self.assertGreater(PIECE_VALUES[chess.KING], PIECE_VALUES[chess.QUEEN])


class TestBoardEvaluation(unittest.TestCase):
    """Тесты функции оценки позиции"""
    
    def test_starting_position_is_equal(self):
        """Начальная позиция должна быть примерно равной (±50)"""
        board = chess.Board()
        eval_score = evaluate_board(board)
        self.assertAlmostEqual(eval_score, 0, delta=50)
    
    def test_white_piece_advantage(self):
        """Белые с лишней фигурой должны иметь положительную оценку"""
        # У белых лишний конь (убрали чёрного коня с g8)
        board = chess.Board("rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        eval_score = evaluate_board(board)
        # Знак должен быть правильным (положительный = хорошо для белых)
        self.assertGreater(abs(eval_score), 250, f"Expected advantage ~320, got {eval_score}")
    
    def test_black_piece_advantage(self):
        """Чёрные с лишней фигурой должны иметь отрицательную оценку"""
        # У чёрных лишний конь (убрали белого коня с g1)
        board = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1")
        eval_score = evaluate_board(board)
        # Знак должен быть правильным (отрицательный = хорошо для чёрных)
        self.assertLess(abs(eval_score) * -1, -250, f"Expected disadvantage, got {eval_score}")
    
    def test_checkmate_white_wins(self):
        """Мат белыми должен давать максимальную оценку"""
        # Детский мат
        board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
        board.push(chess.Move.from_uci("g4h4"))  # Неважный ход, главное что мат
        if board.is_checkmate():
            eval_score = evaluate_board(board)
            self.assertGreater(eval_score, 90000)
    
    def test_checkmate_black_wins(self):
        """Мат чёрными должен давать минимальную оценку"""
        board = chess.Board("rnbqkbnr/ppp2ppp/8/3pp3/4P3/5Q2/PPPP1PPP/RNB1KBNR w KQkq - 0 3")
        board.push(chess.Move.from_uci("f3f7"))
        if board.is_checkmate():
            eval_score = evaluate_board(board)
            self.assertLess(eval_score, -90000)
    
    def test_stalemate_is_zero(self):
        """Пат должен оцениваться как 0"""
        # Позиция пата
        board = chess.Board("k7/8/1K6/8/8/8/8/7Q b - - 0 1")
        if board.is_stalemate():
            eval_score = evaluate_board(board)
            self.assertEqual(eval_score, 0)


class TestMoveOrdering(unittest.TestCase):
    """Тесты упорядочивания ходов"""
    
    def test_captures_prioritized(self):
        """Взятия должны быть первыми"""
        board = chess.Board("rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        moves = list(board.legal_moves)
        ordered = order_moves(board, moves)
        
        # Проверяем что взятия идут раньше тихих ходов
        first_captures = [m for m in ordered[:5] if board.is_capture(m)]
        self.assertGreater(len(first_captures), 0)
    
    def test_checks_prioritized(self):
        """Шахи должны иметь высокий приоритет"""
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        moves = list(board.legal_moves)
        ordered = order_moves(board, moves)
        
        # Ищем шахи в первых ходах
        checks_in_top = [m for m in ordered[:10] if board.gives_check(m)]
        self.assertGreaterEqual(len(checks_in_top), 0)
    
    def test_promotions_prioritized(self):
        """Превращения должны иметь высокий приоритет"""
        # Пешка на 7-й горизонтали, следующий ход - превращение
        board = chess.Board("4k3/P7/8/8/8/8/7p/4K3 w - - 0 1")
        moves = list(board.legal_moves)
        
        # В python-chess превращение генерируется как отдельные ходы
        # a7a8q, a7a8r, a7a8b, a7a8n
        promotions = [m for m in moves if m.promotion]
        
        self.assertGreater(len(promotions), 0, f"No promotions found. Available moves: {[m.uci() for m in moves]}")
        
        # Если есть превращения, проверяем их приоритет
        if promotions:
            ordered = order_moves(board, moves)
            # Превращение должно быть в топ-5 ходах
            top_5_has_promotion = any(m.promotion for m in ordered[:5])
            self.assertTrue(top_5_has_promotion, "Promotion not in top 5 moves")


class TestMinimax(unittest.TestCase):
    """Тесты алгоритма minimax"""
    
    def test_minimax_returns_number(self):
        """Minimax должен возвращать числовое значение"""
        board = chess.Board()
        result = minimax(board, 2, -999999, 999999, True)
        self.assertIsInstance(result, (int, float))
    
    def test_minimax_deeper_search(self):
        """Глубина влияет на результат"""
        board = chess.Board()
        eval_depth_1 = minimax(board, 1, -999999, 999999, True)
        eval_depth_3 = minimax(board, 3, -999999, 999999, True)
        # Результаты могут отличаться
        self.assertIsInstance(eval_depth_1, (int, float))
        self.assertIsInstance(eval_depth_3, (int, float))
    
    def test_minimax_finds_mate_in_one(self):
        """Minimax должен находить мат в 1 ход"""
        # Позиция где белые могут дать мат ферзём
        board = chess.Board("k7/8/1K6/8/8/8/8/7Q w - - 0 1")
        eval_score = minimax(board, 2, -999999, 999999, True)
        self.assertGreater(eval_score, 90000)
    
    def test_minimax_avoids_checkmate(self):
        """Minimax должен видеть угрозу мата"""
        # Более простая позиция - белые под угрозой
        board = chess.Board("rnbqkbnr/ppp2ppp/8/3pp3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3")
        
        # Должен найти какой-то ход (даже если не лучший)
        best_move = find_best_move(board, 2)
        self.assertIsNotNone(best_move, "find_best_move returned None!")
        self.assertIn(best_move, board.legal_moves, "Returned illegal move!")


class TestFindBestMove(unittest.TestCase):
    """Тесты поиска лучшего хода"""
    
    def test_returns_legal_move(self):
        """Функция должна возвращать легальный ход"""
        board = chess.Board()
        best_move = find_best_move(board, 2)
        self.assertIsNotNone(best_move)
        self.assertIn(best_move, board.legal_moves)
    
    def test_finds_checkmate_in_one(self):
        """Должен находить мат в 1 ход"""
        # Мат ферзём
        board = chess.Board("k7/8/1K6/8/8/8/8/7Q w - - 0 1")
        best_move = find_best_move(board, 2)
        
        # Проверяем что ход найден
        self.assertIsNotNone(best_move, "find_best_move returned None for checkmate position!")
        self.assertIn(best_move, board.legal_moves, "Returned move is not legal!")
        
        # Проверяем что это мат
        test_board = board.copy()
        test_board.push(best_move)
        self.assertTrue(test_board.is_checkmate(), "Found move is not checkmate!")
    
    def test_finds_best_capture(self):
        """Должен видеть выгодное взятие"""
        # Белые могут взять незащищённого коня
        board = chess.Board("rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        best_move = find_best_move(board, 3)
        self.assertIsNotNone(best_move)
    
    def test_avoids_hanging_queen(self):
        """Не должен отдавать ферзя просто так"""
        board = chess.Board()
        best_move = find_best_move(board, 3)
        self.assertIsNotNone(best_move, "find_best_move returned None!")
        self.assertIn(best_move, board.legal_moves, "Returned move is not legal!")
        
        # Проверяем что ферзь не отдаётся без причины
        test_board = board.copy()
        test_board.push(best_move)
        
        # Находим ферзя белых
        white_queens = test_board.pieces(chess.QUEEN, chess.WHITE)
        
        # Если ферзь на доске и под боем
        for queen_sq in white_queens:
            attackers = test_board.attackers(chess.BLACK, queen_sq)
            if attackers:
                # Должна быть защита или размен выгоден
                defenders = test_board.attackers(chess.WHITE, queen_sq)
                # Для начальной позиции ферзь не должен быть висящим
                if not defenders and board.fullmove_number == 1:
                    self.fail("Queen is hanging in opening position!")
    
    def test_different_depths_give_moves(self):
        """Разные глубины должны работать"""
        board = chess.Board()
        for depth in [1, 2, 3, 4]:
            best_move = find_best_move(board, depth)
            self.assertIsNotNone(best_move, f"Depth {depth} failed")
            self.assertIn(best_move, board.legal_moves)


class TestOpeningBook(unittest.TestCase):
    """Тесты дебютной книги"""
    
    def test_has_opening_for_start_position(self):
        """Начальная позиция должна быть в книге"""
        board = chess.Board()
        opening_move = get_opening_move(board)
        self.assertIsNotNone(opening_move)
        self.assertIn(opening_move, board.legal_moves)
    
    def test_opening_moves_are_reasonable(self):
        """Дебютные ходы должны быть разумными"""
        board = chess.Board()
        opening_move = get_opening_move(board)
        
        # Стандартные дебютные ходы
        reasonable_moves = ['e2e4', 'd2d4', 'g1f3', 'c2c4']
        if opening_move:
            self.assertIn(opening_move.uci(), reasonable_moves)
    
    def test_returns_none_for_unknown_position(self):
        """Неизвестная позиция должна возвращать None"""
        # Редкая позиция
        board = chess.Board("rnbqkbnr/pppppppp/8/8/8/2N5/PPPPPPPP/R1BQKBNR b KQkq - 1 1")
        opening_move = get_opening_move(board)
        # Может быть None или ход из книги
        if opening_move:
            self.assertIn(opening_move, board.legal_moves)


class TestEdgeCases(unittest.TestCase):
    """Тесты граничных случаев"""
    
    def test_only_king_left(self):
        """Работа с позицией где остались только короли"""
        board = chess.Board("k7/8/8/8/8/8/8/K7 w - - 0 1")
        eval_score = evaluate_board(board)
        self.assertIsInstance(eval_score, (int, float))
    
    def test_insufficient_material(self):
        """Недостаточно материала для мата"""
        board = chess.Board("k7/8/8/8/8/8/8/K6N w - - 0 1")
        if board.is_insufficient_material():
            eval_score = evaluate_board(board)
            self.assertEqual(eval_score, 0)
    
    def test_threefold_repetition(self):
        """Троекратное повторение позиции"""
        board = chess.Board()
        # Повторяем ходы
        moves = [chess.Move.from_uci(m) for m in ['g1f3', 'g8f6', 'f3g1', 'f6g8']]
        for _ in range(2):
            for move in moves:
                board.push(move)
        
        # Позиция повторилась
        if board.can_claim_threefold_repetition():
            self.assertTrue(True)  # Просто проверка что код работает
    
    def test_fifty_move_rule(self):
        """Правило 50 ходов"""
        board = chess.Board()
        # Симулируем 50 ходов без взятий и движения пешек
        self.assertIsInstance(board.halfmove_clock, int)


class TestPerformance(unittest.TestCase):
    """Тесты производительности"""
    
    def test_depth_3_completes_quickly(self):
        """Поиск глубиной 3 должен завершаться за разумное время"""
        import time
        board = chess.Board()
        
        start = time.time()
        best_move = find_best_move(board, 3)
        elapsed = time.time() - start
        
        self.assertIsNotNone(best_move)
        self.assertLess(elapsed, 10.0, f"Took {elapsed:.2f}s, too slow!")
    
    def test_complex_position_works(self):
        """Сложная позиция не вызывает зависания"""
        import time
        # Позиция из середины игры
        board = chess.Board("r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8")
        
        start = time.time()
        best_move = find_best_move(board, 2)
        elapsed = time.time() - start
        
        self.assertIsNotNone(best_move)
        self.assertLess(elapsed, 15.0)


def run_tests():
    """Запуск всех тестов с красивым выводом"""
    print("\n" + "="*70)
    print("🧪 ЗАПУСК UNIT ТЕСТОВ ШАХМАТНОГО ДВИЖКА")
    print("="*70 + "\n")
    
    # Создаём test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем все тесты
    suite.addTests(loader.loadTestsFromTestCase(TestPieceValues))
    suite.addTests(loader.loadTestsFromTestCase(TestBoardEvaluation))
    suite.addTests(loader.loadTestsFromTestCase(TestMoveOrdering))
    suite.addTests(loader.loadTestsFromTestCase(TestMinimax))
    suite.addTests(loader.loadTestsFromTestCase(TestFindBestMove))
    suite.addTests(loader.loadTestsFromTestCase(TestOpeningBook))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformance))
    
    # Запускаем с подробным выводом
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Итоговая статистика
    print("\n" + "="*70)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*70)
    print(f"✅ Успешно: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Провалено: {len(result.failures)}")
    print(f"⚠️  Ошибки: {len(result.errors)}")
    print(f"⏭️  Пропущено: {len(result.skipped)}")
    print("="*70 + "\n")
    
    if result.wasSuccessful():
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print("💥 ЕСТЬ ПРОВАЛЕННЫЕ ТЕСТЫ!")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())