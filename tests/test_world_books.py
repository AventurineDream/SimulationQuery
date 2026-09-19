from improv_troupe.application.world_books import WorldBookEngine
from improv_troupe.domain import WorldBook, WorldBookEntry


def test_world_book_activation_preserves_private_boundaries_and_recurses():
    book = WorldBook(
        world_book_id="test", name="Test", recursive_scanning=True, token_budget=30,
        entries=[
            WorldBookEntry(entry_id="shared", name="Archive", keys=["archive"], content="The archive contains an amber key."),
            WorldBookEntry(entry_id="recursive", name="Amber", keys=["amber"], content="Amber keys open the old lock."),
            WorldBookEntry(entry_id="private", name="Secret", keys=["archive"], visibility="CHARACTER_PRIVATE", character_ids=["luna"], content="Luna recognizes the maker."),
            WorldBookEntry(entry_id="director", name="Truth", keys=["archive"], visibility="DIRECTOR_ONLY", content="The archive is alive."),
        ],
    )
    engine = WorldBookEngine()

    mason = engine.activate((book,), text="We found the archive.", recipient="mason")
    assert {item.entry_id for item in mason} == {"shared", "recursive"}
    luna = engine.activate((book,), text="We found the archive.", recipient="luna")
    assert "private" in {item.entry_id for item in luna}
    director = engine.activate((book,), text="We found the archive.", recipient="__orchestrator__", is_director=True)
    assert "director" in {item.entry_id for item in director}


def test_world_book_respects_budget():
    book = WorldBook(
        world_book_id="test", name="Test", token_budget=3,
        entries=[WorldBookEntry(entry_id="large", name="Large", keys=["key"], content="one two three four")],
    )
    assert WorldBookEngine().activate((book,), text="key", recipient="anyone") == ()
