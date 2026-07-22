from functools import partial
from checks import (
    check_used_legal_hint,
    check_no_false_claims,
    check_no_irrelevant_moves,
    check_intent_followed_by_action,
    check_input_square_translation,
    check_no_invented_rules,
    check_move_description_accuracy,
    check_turn_efficiency,
    check_recalls_first_move,
)

SCENARIOS = [
    {
        "id": "blind_retry_knight_b1b3",
        "category": "illegal_move_correction",
        "start_fen": None,
        "user_prompt": (
            "I want to move my knight from b1 to b3. If that's not a "
            "legal move, figure out a legal knight move instead and play it."
        ),
        "check_fns": {
            "used_legal_hint": check_used_legal_hint,
            "intent_action_consistency": check_intent_followed_by_action,
            "no_invented_rules": check_no_invented_rules,
            "move_description_accuracy": check_move_description_accuracy,
            "turn_efficiency": check_turn_efficiency,
        },
    },
    {
        "id": "bishop_c1a3_multi",
        "category": "illegal_move_correction",
        "start_fen": None,
        "user_prompt": (
            "I want to move my bishop from c1 to a3. If that's not a "
            "legal move, figure out a legal bishop move instead and play it."
        ),
        "check_fns": {
            "used_legal_hint": check_used_legal_hint,
            "no_false_claims": check_no_false_claims,
            "intent_action_consistency": check_intent_followed_by_action,
            "input_square_translation": partial(check_input_square_translation, expected_origin_square="c1"),
            "no_irrelevant_moves": partial(check_no_irrelevant_moves, expected_origin_square="c1"),
            "no_invented_rules": check_no_invented_rules,
            "move_description_accuracy": check_move_description_accuracy,
            "turn_efficiency": check_turn_efficiency,
        },
    },
    {
        "id": "memory_depth_two_moves",
        "category": "conversation_memory",
        "start_fen": None,
        "user_prompts": [
            "Play e2e4.",
            "Now play e7e5 for black.",
            "What was the very first move of this game?",
        ],
        "check_fns": {
            "recalls_first_move": check_recalls_first_move,
        },
    },
]