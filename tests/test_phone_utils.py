from bot.phone_utils import hash_phone, mask_phone, normalize_phone


def test_normalize_phone_success() -> None:
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"


def test_normalize_phone_fail() -> None:
    assert normalize_phone("12345") is None


def test_mask_phone() -> None:
    assert mask_phone("+79991234567") == "+79*****4567"


def test_hash_phone_stable() -> None:
    value_1 = hash_phone("+79991234567", "salt12345")
    value_2 = hash_phone("+79991234567", "salt12345")
    assert value_1 == value_2
    assert len(value_1) == 64
