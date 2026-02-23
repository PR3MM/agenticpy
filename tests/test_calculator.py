from app.calculator import calculate_mean

def test_calculate_mean():
    data = [10, 20, 30]
    result = calculate_mean(data)
    assert result == 20.0
