"""Stable storage facade."""
from backend import database

get_connection = database.get_connection
init_db = database.init_db
save_conversation = database.save_conversation
save_audit_log = database.save_audit_log
save_form_submission = database.save_form_submission
get_form_submission = getattr(database, "get_form_submission", None)
update_form_submission_status = getattr(database, "update_form_submission_status", None)
