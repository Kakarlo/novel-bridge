from .balanced import BALANCED_PROFILE
from .low import LOW_PROFILE
from .premium import PREMIUM_PROFILE


def get_profile(name: str):
    match name:
        case "low":
            return LOW_PROFILE

        case "premium":
            return PREMIUM_PROFILE

        case _:
            return BALANCED_PROFILE
