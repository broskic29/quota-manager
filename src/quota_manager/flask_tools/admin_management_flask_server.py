from flask import Flask, request, render_template_string, redirect, url_for
from sqlite3 import IntegrityError
import logging

import quota_manager.sql_management as sqlm
import quota_manager.quota_management as qm
import quota_manager.sqlite_helper_functions as sqlh
import quota_manager.flask_tools.flask_utils as flu

import quota_manager.flask_tools.admin_html as ahtml

from types import SimpleNamespace
import datetime as dt


admin_management_app = Flask(__name__)

log = logging.getLogger(__name__)

DEFAULT_PASSWORD = "password"


@admin_management_app.route("/admin")
@flu.require_admin_auth
def admin_home():
    return render_template_string(ahtml.admin_landing_page)


@admin_management_app.route("/admin/new_user", methods=["GET", "POST"])
@flu.require_admin_auth
def create_user():
    error = None
    existing_groups = []

    existing_groups, error = flu.safe_call(
        sqlm.get_groups_usage,
        error,
        None,
    )

    if error:
        return render_template_string(
            ahtml.new_user_form, groups=existing_groups, error=error
        )

    if request.method == "POST":
        data = request.form
        username = data.get("username")
        group_name = data.get("group_name")

        error = flu.error_appender(error, flu.validate_name(username, "Username"))

        error = flu.error_appender(error, flu.validate_name(group_name, "Group Name"))
        if error:
            return render_template_string(
                ahtml.new_user_form, groups=existing_groups, error=error
            )

        USER_CREATION_ERROR_MESSAGES = {
            sqlm.UserNameError: f"Failed to create user {username}: User already exists.\n",
            sqlm.GroupNameError: f"Failed inserting user {username} into group {group_name}: No group by name {group_name} exists.\n",
            IntegrityError: f"Failed to create user {username}: User already exists.\n",
            qm.QuotaAllottmentError: None,
            qm.RestrictedDayError: None,
            flu.UndefinedException: f"Internal error creating user {username}. Please reload page.\n",
        }

        _, error = flu.safe_call(
            qm.create_user,
            error,
            USER_CREATION_ERROR_MESSAGES,
            username,
            DEFAULT_PASSWORD,
            group_name,
        )

        if error:
            return render_template_string(
                ahtml.new_user_form, groups=existing_groups, error=error
            )

        log.info(
            f"Succesfully created user {username} and assigned to group {group_name}."
        )
        return render_template_string(
            ahtml.success_page, message="User creation successul!"
        )

    return render_template_string(
        ahtml.new_user_form, groups=existing_groups, error=error
    )


@admin_management_app.route("/admin/new_group", methods=["GET", "POST"])
@flu.require_admin_auth
def create_group():
    error = None
    if request.method == "POST":
        data = request.form
        group_name = data.get("group_name")
        desired_quota_ratio = float(request.form.get("desired_quota_ratio"))

        error = flu.error_appender(error, flu.validate_name(group_name, "Group name"))

        GROUP_CREATION_ERROR_MESSAGES = {
            IntegrityError: f"Failed to create group {group_name}: Group already exists.\n",
            ValueError: None,
            qm.QuotaAllottmentError: None,
            flu.UndefinedException: f"Internal error creating user {group_name}. Please reload page.\n",
        }

        quota_ratio_legal, error = flu.safe_call(
            qm.check_quota_ratio_legality,
            error,
            GROUP_CREATION_ERROR_MESSAGES,
            desired_quota_ratio,
        )

        if error:
            return render_template_string(
                ahtml.new_group_form,
                error=error,
            )

        if quota_ratio_legal:
            _, error = flu.safe_call(
                sqlm.create_group_usage,
                error,
                GROUP_CREATION_ERROR_MESSAGES,
                group_name,
                desired_quota_ratio,
            )

            if error:
                return render_template_string(
                    ahtml.new_group_form,
                    error=error,
                )

            log.info(f"Succesfully created group {group_name}.")
            return render_template_string(
                ahtml.success_page, message="Group creation successul!"
            )

    return render_template_string(
        ahtml.new_group_form,
        error=error,
    )


@admin_management_app.route("/admin/usage")
@flu.require_admin_auth
def usage_overview():
    return "<h2>Usage overview coming soon</h2>"


@admin_management_app.route("/")
def root():
    return redirect(url_for("admin_home"))


@admin_management_app.route("/admin/users")
@flu.require_admin_auth
def manage_users():
    users = sqlm.fetch_all_usernames_usage()
    return render_template_string(ahtml.manage_users_page, users=users or [])


@admin_management_app.route("/admin/users/<username>/delete", methods=["POST"])
@flu.require_admin_auth
def delete_user(username):
    error = None
    USER_DELETE_ERROR_MESSAGES = {
        sqlm.UserNameError: f"User {username} does not exist.\n",
        flu.UndefinedException: f"Internal error deleting user {username}.\n",
    }
    _, error = flu.safe_call(
        qm.delete_user_from_system, error, USER_DELETE_ERROR_MESSAGES, username
    )
    if error:
        return render_template_string(ahtml.success_page, message=error)
    return render_template_string(
        ahtml.success_page, message=f"Deleted user {username}."
    )


@admin_management_app.route("/admin/groups")
@flu.require_admin_auth
def manage_groups():
    rows = sqlm.fetch_group_quota_info_usage()
    # rows: (group_name, num_members, desired_quota_ratio, min_quota_ratio, max_num_bytes, min_num_bytes, mse_weights)
    groups = [
        SimpleNamespace(
            group_name=r[0],
            num_members=r[1],
            desired_quota_ratio=r[2],
        )
        for r in (rows or [])
    ]
    return render_template_string(ahtml.manage_groups_page, groups=groups)


@admin_management_app.route("/admin/groups/<group_name>/ratio", methods=["POST"])
@flu.require_admin_auth
def update_group_ratio(group_name):
    error = None
    try:
        desired_quota_ratio = float(request.form.get("desired_quota_ratio"))
    except Exception:
        return render_template_string(ahtml.success_page, message="Invalid ratio.")

    # validate legality using your existing check
    GROUP_UPDATE_ERROR_MESSAGES = {
        ValueError: None,
        qm.QuotaAllottmentError: None,
        flu.UndefinedException: "Internal error updating group ratio.\n",
    }

    # Problem: If ratios already = 1, then lowering is incorrectly calculating legality as if you
    # were adding the lowered ratio to the ratios that already sum to 1. Need to
    # fix.
    _, error = flu.safe_call(
        qm.check_quota_ratio_legality,
        error,
        GROUP_UPDATE_ERROR_MESSAGES,
        desired_quota_ratio,
        group_name,
    )
    if error:
        return render_template_string(ahtml.success_page, message=error)

    sqlm.update_group_desired_quota_ratio(group_name, desired_quota_ratio)

    # Recompute quotas immediately so admin sees it “take”
    tz = dt.timezone(dt.timedelta(hours=sqlh.UTC_OFFSET))
    now = dt.datetime.now(tz)
    try:
        qm.update_group_quotas(now, qm.ACCOUNT_BILLING_DAY)
    except Exception:
        log.exception("Non-fatal: quota recompute failed after ratio update.")

    return redirect(url_for("manage_groups"))


@admin_management_app.route("/admin/groups/<group_name>/delete", methods=["POST"])
@flu.require_admin_auth
def delete_group(group_name):
    members = sqlm.count_users_in_group(group_name)
    if members > 0:
        return render_template_string(
            ahtml.success_page,
            message=f"Cannot delete group '{group_name}' because it has {members} users.",
        )

    sqlm.delete_group_usage(group_name)
    return redirect(url_for("manage_groups"))
