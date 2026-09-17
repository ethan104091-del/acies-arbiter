from acies.db import models as M


def emit(db, table_id, kind, gh=None, **payload):
    db.add(M.Event(table_id=table_id, kind=kind, gh=gh, payload=payload))
