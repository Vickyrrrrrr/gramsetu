"""Stable storage facade — delegates to backend.database (Supabase)."""
from backend import database

get_connection               = database.get_connection
init_db                      = database.init_db
log_conversation             = database.log_conversation
save_conversation            = database.save_conversation
log_audit                    = database.log_audit
save_audit_log               = database.save_audit_log
save_form_submission         = database.save_form_submission
get_form_submission          = database.get_form_submission
update_form_submission_status = database.update_form_submission_status
confirm_submission           = database.confirm_submission
reject_submission            = database.reject_submission
get_pending_submissions      = database.get_pending_submissions
get_all_submissions          = database.get_all_submissions
get_session                  = database.get_session
set_session                  = database.set_session
get_stats                    = database.get_stats
get_recent_conversations     = database.get_recent_conversations
get_audit_logs               = database.get_audit_logs
