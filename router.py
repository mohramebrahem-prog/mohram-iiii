# -*- coding: utf-8 -*-
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, user_handlers, admin_handlers,
                 eng_handler=None, vid_handler=None,
                 ctrl_handler=None, sm_handler=None,
                 flash_handler=None):
        self.u    = user_handlers
        self.a    = admin_handlers
        self.eng  = eng_handler
        self.vid  = vid_handler
        self.ctrl = ctrl_handler
        self.sm   = sm_handler
        self.flash = flash_handler

    async def handle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q    = update.callback_query
        data = q.data or ""
        uid  = update.effective_user.id

        if not self.u.db.is_subscribed(uid, self.u.admin_ids):
            if data not in ("enter_sub_code","main_menu"):
                await q.answer("🔒 اشتراكك منتهٍ.", show_alert=True)
                await self.u.show_sub_required(update, ctx)
                return

        try:
            await q.answer()
        except Exception:
            pass

        try:
            # ── رئيسي ────────────────────────────────────────────
            if   data == "main_menu":             await self.u.show_main(update, ctx)
            elif data == "enter_sub_code":        await self.u.enter_code_prompt(update, ctx)

            # ── أرقام ─────────────────────────────────────────────
            elif data == "manage_numbers":        await self.u.manage_numbers_menu(update, ctx)
            elif data == "add_number":            await self.u.add_number_start(update, ctx)
            elif data == "list_numbers":          await self.u.list_numbers(update, ctx)
            elif data == "check_number":          await self.u.check_number_start(update, ctx)
            elif data == "delete_number":         await self.u.delete_number_start(update, ctx)
            elif data == "delete_number_final":   await self.u.delete_number_final(update, ctx)
            elif data == "switch_number":         await self.u.switch_number_start(update, ctx)
            elif data == "switch_number_confirm": await self.u.switch_number_confirm(update, ctx)
            elif data == "security_tips_numbers": await self.u.security_tips_numbers(update, ctx)
            elif data.startswith("check_number_do_"):
                await self.u.check_number_do(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("delete_number_confirm_"):
                await self.u.delete_number_confirm(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("switch_number_select_"):
                await self.u.switch_number_select(update, ctx, int(data.split("_")[-1]))

            # ── نشر ───────────────────────────────────────────────
            elif data == "publish_engine":        await self.u.publish_engine_menu(update, ctx)
            elif data == "publish_start":         await self.u.publish_start(update, ctx)
            elif data == "publish_stop":          await self.u.publish_stop(update, ctx)
            elif data == "publish_pause":         await self.u.publish_pause(update, ctx)
            elif data == "publish_resume":        await self.u.publish_resume(update, ctx)
            elif data == "pub_stats":             await self.u.pub_stats(update, ctx)
            elif data == "pub_select_numbers":    await self.u.pub_select_numbers(update, ctx)
            elif data == "pub_select_all_nums":
                nums = [n for n in self.u.db.get_user_numbers(uid) if n["is_active"]]
                ctx.user_data["pub_selected_numbers"] = [n["id"] for n in nums]
                await self.u.pub_select_numbers(update, ctx)
            elif data == "pub_deselect_all_nums":
                ctx.user_data["pub_selected_numbers"] = []
                await self.u.pub_select_numbers(update, ctx)
            elif data == "pub_select_ads":        await self.u.pub_select_ads(update, ctx)
            elif data == "publish_ads_menu":      await self.u.publish_ads_menu(update, ctx)
            elif data == "publish_new_ad":        await self.u.publish_new_ad_start(update, ctx)
            elif data == "publish_settings_menu": await self.u.publish_settings_menu(update, ctx)
            elif data == "toggle_deduplicate":    await self.u.toggle_deduplicate(update, ctx)
            elif data == "smart_publish_menu":    await self.u.smart_publish_menu(update, ctx)
            elif data == "publish_safety_tips":   await self.u.publish_safety_tips(update, ctx)
            elif data.startswith("pub_toggle_num_"):
                await self.u.pub_toggle_number(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("pub_toggle_ad_"):
                await self.u.pub_toggle_ad(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("publish_delete_ad_"):
                await self.u.publish_delete_ad(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("set_pub_"):
                await self.u.publish_setting_edit_start(update, ctx, data[8:])
            elif data.startswith("smart_pub_"):
                await self.u.smart_publish_start(update, ctx, data[10:])

            # ══ 📁 إدارة المجلدات ══════════════════════════════════
            elif data == "folder_dashboard":
                await self.u.folder_dashboard(update, ctx)
            elif data.startswith("folder_number_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_number_control(update, ctx, nid)
            elif data.startswith("folder_create_start_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_create_start(update, ctx, nid)
            elif data.startswith("folder_type_"):
                parts = data.split("_")
                ftype = parts[2]
                nid   = int(parts[3])
                await self.u.folder_set_type(update, ctx, nid, ftype)
            elif data.startswith("folder_list_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_list(update, ctx, nid)
            elif data.startswith("folder_detail_"):
                parts     = data.split("_")
                folder_id = int(parts[2])
                nid       = int(parts[3])
                await self.u.folder_detail(update, ctx, folder_id, nid)
            elif data.startswith("folder_del_only_"):
                parts     = data.split("_")
                folder_id = int(parts[3])
                nid       = int(parts[4])
                await self.u.folder_delete_only(update, ctx, folder_id, nid)
            elif data.startswith("folder_del_leave_"):
                parts     = data.split("_")
                folder_id = int(parts[3])
                nid       = int(parts[4])
                await self.u.folder_delete_and_leave(update, ctx, folder_id, nid)
            elif data == "folder_confirm_delete":
                await self.u.folder_confirm_delete(update, ctx)
            elif data.startswith("folder_clean_"):
                if "confirm" in data:
                    nid = int(data.split("_")[-1])
                    await self.u.folder_clean_confirm(update, ctx, nid)
                else:
                    nid = int(data.split("_")[-1])
                    await self.u.folder_clean_start(update, ctx, nid)
            elif data == "folder_stop_task":
                await self.u.folder_stop_task(update, ctx)
            elif data.startswith("folder_safety_settings_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_safety_settings(update, ctx, nid)
            elif data.startswith("folder_safety_preset_"):
                parts  = data.split("_")
                preset = parts[3]
                nid    = int(parts[4])
                await self.u.folder_safety_preset(update, ctx, preset, nid)
            elif data.startswith("set_folder_delay_min_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_safety_set_start(update, ctx, "join_delay_min", nid)
            elif data.startswith("set_folder_delay_max_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_safety_set_start(update, ctx, "join_delay_max", nid)
            elif data.startswith("set_folder_break_dur_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_safety_set_start(update, ctx, "big_break_duration", nid)
            elif data.startswith("set_folder_gpb_"):
                nid = int(data.split("_")[-1])
                await self.u.folder_safety_set_start(update, ctx, "groups_per_break", nid)

            # ── حماية الإعلان ─────────────────────────────────────
            elif data == "ad_protect_menu":          await self.u.ad_protect_menu(update, ctx)
            elif data == "ad_protect_lvl_1":         await self.u.ad_protect_set_level(update, ctx, 1)
            elif data == "ad_protect_lvl_2":         await self.u.ad_protect_set_level(update, ctx, 2)
            elif data == "ad_protect_lvl_3":         await self.u.ad_protect_set_level(update, ctx, 3)

            # ── جلب ──────────────────────────────────────────────
            elif data == "fetch_links_menu":         await self.u.fetch_links_menu(update, ctx)
            elif data == "fetch_select_number":      await self.u.fetch_select_number(update, ctx)
            elif data == "fetch_select_type":        await self.u.fetch_select_type(update, ctx)
            elif data == "fetch_date_settings":      await self.u.fetch_date_settings(update, ctx)
            elif data == "fetch_mode_my_groups":     await self.u.fetch_mode_my_groups(update, ctx)
            elif data == "fetch_mode_messages":      await self.u.fetch_mode_messages(update, ctx)
            elif data == "fetch_mode_all":           await self.u.fetch_mode_all(update, ctx)
            elif data == "fetch_start":              await self.u.fetch_start(update, ctx)
            elif data == "fetch_stop":               await self.u.fetch_stop(update, ctx)
            elif data == "fetch_clear_memory":       await self.u.fetch_clear_memory(update, ctx)
            elif data == "fetch_help":               await self.u.fetch_help(update, ctx)
            elif data.startswith("fetch_set_number_"):
                await self.u.fetch_set_number(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("fetch_type_"):
                await self.u.fetch_set_type(update, ctx, data[11:])
            elif data.startswith("fetch_setdate_"):
                await self.u.fetch_setdate_handler(update, ctx, int(data.split("_")[-1]))

            # ── ردود ─────────────────────────────────────────────
            elif data == "auto_reply":               await self.u.auto_reply_menu(update, ctx)
            elif data == "auto_reply_add":           await self.u.auto_reply_add_start(update, ctx)
            elif data == "auto_reply_list":          await self.u.auto_reply_list(update, ctx)

            # ── حساب ─────────────────────────────────────────────
            elif data == "my_account":               await self.u.my_account_menu(update, ctx)
            elif data == "referrals":                await self.u.referrals_menu(update, ctx)
            elif data == "help":                     await self.u.help_menu(update, ctx)
            elif data == "bot_tutorial":             await self.u.bot_tutorial(update, ctx)

            # ══════════════ أدمن — كامل ══════════════════════════
            elif data == "admin_panel":              await self.a.admin_panel(update, ctx)

            # إدارة المستخدمين
            elif data == "admin_manage_users":       await self.a.admin_manage_users(update, ctx)
            elif data == "admin_list_users":         await self.a.admin_list_users(update, ctx)
            elif data == "admin_list_subscribed":    await self.a.admin_list_subscribed(update, ctx)
            elif data == "admin_list_banned":        await self.a.admin_list_banned(update, ctx)
            elif data == "admin_users_activity":     await self.a.admin_users_activity(update, ctx)
            elif data == "admin_search_user":        await self.a.admin_search_user(update, ctx)
            elif data == "user_page_next":           await self.a.user_page_nav(update, ctx, "next")
            elif data == "user_page_prev":           await self.a.user_page_nav(update, ctx, "prev")
            elif data.startswith("show_user_"):
                await self.a.show_user_details(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_ban_user_"):
                await self.a.admin_ban_user(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_unban_user_"):
                await self.a.admin_unban_user(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_delete_user_"):
                await self.a.admin_delete_user(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_confirm_delete_user_"):
                await self.a.admin_confirm_delete_user(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_extend_user_"):
                await self.a.admin_extend_user_prompt(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_user_numbers_"):
                await self.a.admin_user_numbers(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("admin_user_activity_"):
                await self.a.admin_user_activity(update, ctx, int(data.split("_")[-1]))

            # مراقبة النشاط
            elif data == "admin_activity":           await self.a.admin_activity(update, ctx)
            elif data == "admin_activity_live":      await self.a.admin_activity_live(update, ctx)
            elif data == "admin_activity_today":     await self.a.admin_activity_today(update, ctx)
            elif data == "admin_activity_week":      await self.a.admin_activity_week(update, ctx)
            elif data == "admin_active_now":         await self.a.admin_active_now(update, ctx)

            # إدارة الأكواد
            elif data == "admin_manage_codes":       await self.a.admin_manage_codes(update, ctx)
            elif data == "admin_add_code":           await self.a.admin_add_code_prompt(update, ctx)
            elif data == "admin_trial_code":         await self.a.admin_trial_code(update, ctx)
            elif data == "admin_list_codes":         await self.a.admin_list_codes(update, ctx)
            elif data == "admin_list_codes_full":    await self.a.admin_list_codes_full(update, ctx)
            elif data == "admin_codes_report":       await self.a.admin_codes_report(update, ctx)
            elif data == "admin_export_codes":       await self.a.admin_export_codes(update, ctx)
            elif data == "admin_add_code_manual":    await self.a.admin_add_code_manual(update, ctx)
            elif data == "admin_sales_report":       await self.a.admin_sales_report(update, ctx)
            elif data == "admin_delete_code":        await self.a.admin_delete_code_prompt(update, ctx)
            elif data == "admin_live_codes":          await self.a.admin_live_codes(update, ctx)
            elif data == "admin_purge_no_code":       await self.a.admin_purge_no_code(update, ctx)
            elif data == "admin_purge_exec":          await self.a.admin_purge_execute(update, ctx)
            elif data.startswith("delete_code_"):
                await self.a.handle_delete_code(update, ctx, data[12:])
            elif data.startswith("admin_rev_exec_"):
                rest = data[len("admin_rev_exec_"):]
                sep  = rest.index("_")
                await self.a.admin_revoke_execute(update, ctx, int(rest[:sep]), rest[sep+1:])
            elif data.startswith("admin_rev_"):
                rest = data[len("admin_rev_"):]
                sep  = rest.index("_")
                await self.a.admin_revoke_confirm(update, ctx, int(rest[:sep]), rest[sep+1:])
            elif data.startswith("trial_"):
                m = {"trial_3h":3,"trial_12h":12,"trial_1d":24,"trial_2d":48}
                if data in m: await self.a.handle_trial_selection(update, ctx, m[data])

            # نظام الإذاعة
            elif data == "admin_broadcast_menu":     await self.a.admin_broadcast_menu(update, ctx)
            elif data == "admin_broadcast":          await self.a.admin_broadcast(update, ctx)
            elif data == "admin_broadcast_all":      await self.a.admin_broadcast_all(update, ctx)
            elif data == "admin_broadcast_announce": await self.a.admin_broadcast_announce(update, ctx)
            elif data == "admin_broadcast_update":   await self.a.admin_broadcast_update(update, ctx)
            elif data == "admin_broadcast_subscribed": await self.a.admin_broadcast_subscribed(update, ctx)

            # إدارة الأرقام
            elif data == "admin_numbers_menu":       await self.a.admin_numbers_menu(update, ctx)
            elif data == "admin_active_numbers":     await self.a.admin_active_numbers(update, ctx)
            elif data == "admin_numbers_stats":      await self.a.admin_numbers_stats(update, ctx)
            elif data == "admin_banned_numbers":     await self.a.admin_banned_numbers(update, ctx)
            elif data == "admin_risky_numbers":      await self.a.admin_risky_numbers(update, ctx)

            # إدارة البوت
            elif data == "admin_bot_control":        await self.a.admin_bot_control(update, ctx)
            elif data == "admin_restart":            await self.a.admin_restart(update, ctx)
            elif data == "admin_stop_bot":           await self.a.admin_stop_bot(update, ctx)
            elif data == "admin_start_bot":          await self.a.admin_start_bot(update, ctx)
            elif data == "admin_clean_sessions":     await self.a.admin_clean_sessions(update, ctx)
            elif data == "admin_error_log":          await self.a.admin_error_log(update, ctx)

            # نظام الأمان
            elif data == "admin_security":           await self.a.admin_security(update, ctx)
            elif data == "admin_threat_radar":       await self.a.admin_threat_radar(update, ctx)
            elif data == "admin_spam_detect":        await self.a.admin_spam_detect(update, ctx)
            elif data == "admin_req_monitor":        await self.a.admin_req_monitor(update, ctx)
            elif data == "admin_manage_perms":       await self.a.admin_manage_perms(update, ctx)

            # مراقبة السيرفر
            elif data == "admin_server_status":      await self.a.admin_server_status(update, ctx)

            # قاعدة البيانات
            elif data == "admin_database_menu":      await self.a.admin_database_menu(update, ctx)
            elif data == "admin_export_db":          await self.a.admin_export_db(update, ctx)
            elif data == "admin_import_db":          await self.a.admin_import_db(update, ctx)
            elif data == "admin_clean_db":           await self.a.admin_clean_db(update, ctx)
            elif data == "admin_analyze_db":         await self.a.admin_analyze_db(update, ctx)

            # الإعدادات
            elif data == "admin_bot_settings":       await self.a.admin_bot_settings(update, ctx)
            elif data == "admin_edit_price":         await self.a.admin_edit_price(update, ctx)
            elif data == "admin_edit_payment":       await self.a.admin_edit_payment(update, ctx)
            elif data == "admin_edit_whatsapp":      await self.a.admin_edit_whatsapp(update, ctx)
            elif data == "admin_edit_code_expiry":   await self.a.admin_edit_code_expiry(update, ctx)

            # النصوص
            elif data == "admin_edit_texts":         await self.a.admin_edit_texts(update, ctx)
            elif data.startswith("edit_text_"):      await self.a.edit_text_prompt(update, ctx, data[10:])

            # التوكين الاحتياطي
            elif data == "admin_backup_token":       await self.a.admin_backup_token(update, ctx)
            elif data == "admin_set_mirror_token":   await self.a.admin_set_mirror_token(update, ctx)
            elif data == "admin_activate_mirror":    await self.a.admin_activate_mirror(update, ctx)

            # البروكسي
            elif data == "admin_proxy_menu":         await self.a.admin_proxy_menu(update, ctx)
            elif data == "admin_add_proxy":          await self.a.admin_add_proxy_prompt(update, ctx)
            elif data == "admin_toggle_proxy":       await self.a.admin_toggle_proxy_prompt(update, ctx)
            elif data.startswith("toggle_proxy_"):
                await self.a.toggle_proxy(update, ctx, int(data.split("_")[-1]))

            # المساعدون
            elif data == "admin_manage_assistants":  await self.a.admin_manage_assistants(update, ctx)
            elif data == "admin_add_assistant":      await self.a.admin_add_assistant_prompt(update, ctx)

            # ══ نظام المهندس الذكي v2 ════════════════════════════
            elif data == "eng_smart_ads_menu":            await self.eng.smart_ads_menu(update, ctx)
            elif data == "eng_manual_encrypt":            await self.eng.eng_manual_encrypt(update, ctx)
            # آدمن المهندس
            elif data == "eng_admin_menu":                await self.eng.admin_engineer_menu(update, ctx)
            elif data == "eng_admin_templates":           await self.eng.admin_templates_list(update, ctx)
            elif data == "eng_admin_del_template":        await self.eng.admin_del_template_prompt(update, ctx)
            elif data == "eng_admin_test_template":       await self.eng.admin_test_template_prompt(update, ctx)
            elif data == "eng_admin_add_bot":             await self.eng.admin_add_bot_prompt(update, ctx)
            elif data == "eng_admin_set_timeout":         await self.eng.admin_set_timeout_prompt(update, ctx)
            elif data == "eng_admin_update_zws":          await self.eng.admin_update_zws_prompt(update, ctx)
            elif data == "eng_admin_notify_vuln":         await self.eng.admin_notify_vuln(update, ctx)
            elif data == "eng_admin_capture":            await self.eng.admin_capture_prompt(update, ctx)
            elif data == "eng_admin_add_manual_tpl":      await self.eng.admin_add_manual_template_prompt(update, ctx)
            elif data.startswith("eng_approve_tpl_"):
                await self.eng.admin_approve_template(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("eng_del_tpl_"):
                await self.eng.admin_del_template(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("eng_disable_code_"):
                await self.eng.admin_disable_user_code(update, ctx, int(data.split("_")[-1]))
            # ══ فيديوهات تعليمية ════════════════════════════════
            elif data == "vid_menu":                      await self.vid.videos_menu(update, ctx)
            elif data == "vid_admin_menu":                await self.vid.admin_videos_menu(update, ctx)
            elif data == "vid_admin_list":                await self.vid.admin_list_videos(update, ctx)
            elif data == "vid_admin_add_url":             await self.vid.admin_add_video_url_start(update, ctx)
            elif data == "vid_admin_add_file":            await self.vid.admin_add_video_file_start(update, ctx)
            elif data == "vid_admin_delete":              await self.vid.admin_delete_video_prompt(update, ctx)
            elif data.startswith("vid_watch_"):
                await self.vid.video_watch(update, ctx, int(data.split("_")[-1]))
            elif data.startswith("vid_del_"):
                await self.vid.admin_delete_video(update, ctx, int(data.split("_")[-1]))
            # ══ مفاتيح تحكم الأنظمة ══════════════════════════════
            elif data == "ctrl_panel":                    await self.ctrl.admin_control_panel(update, ctx)
            elif data == "ctrl_resume_status":            await self.ctrl.ctrl_resume_status(update, ctx)
            elif data.startswith("ctrl_toggle_"):
                await self.ctrl.ctrl_toggle(update, ctx, data[12:])
            # ══ إدارة الجلسات والأكواد ════════════════════════════
            elif data == "sm_logout":                     await self.sm.user_logout_prompt(update, ctx)
            elif data == "sm_confirm_logout":             await self.sm.user_confirm_logout(update, ctx)
            elif data == "sm_revoke_menu":                await self.sm.admin_revoke_code_menu(update, ctx)
            elif data.startswith("sm_revoke_confirm_"):
                parts = data.split("_")
                await self.sm.admin_revoke_confirm(update, ctx, int(parts[3]), parts[4])
            elif data.startswith("sm_revoke_execute_"):
                parts = data.split("_")
                await self.sm.admin_revoke_execute(update, ctx, int(parts[3]), parts[4])

            # ══ Flash Turbo Engine ════════════════════════════════
            elif data == "flash_menu":            await self.flash.flash_menu(update, ctx)
            elif data == "flash_start":           await self.flash.flash_start(update, ctx)
            elif data == "flash_stop":            await self.flash.flash_stop(update, ctx)
            elif data == "flash_sel_nums":        await self.flash.flash_sel_nums(update, ctx)
            elif data == "flash_sel_ads":         await self.flash.flash_sel_ads(update, ctx)
            elif data == "flash_num_all":         await self.flash.flash_num_all(update, ctx)
            elif data == "flash_num_none":        await self.flash.flash_num_none(update, ctx)
            elif data == "flash_ad_all":          await self.flash.flash_ad_all(update, ctx)
            elif data == "flash_ad_none":         await self.flash.flash_ad_none(update, ctx)
            elif data == "flash_ad_bank":         await self.flash.flash_ad_bank(update, ctx)
            elif data == "flash_ad_add":          await self.flash.flash_ad_add_prompt(update, ctx)
            elif data == "flash_ad_del_list":     await self.flash.flash_ad_del_list(update, ctx)
            elif data == "flash_settings":        await self.flash.flash_settings(update, ctx)
            elif data == "flash_live":            await self.flash.flash_live(update, ctx)
            elif data == "flash_radar":           await self.flash.flash_radar(update, ctx)
            elif data == "flash_toggle_24_7":     await self.flash.flash_toggle_24_7(update, ctx)
            elif data == "flash_clean_menu":      await self.flash.flash_clean_menu(update, ctx)
            elif data == "flash_clean_dup":       await self.flash.flash_clean_dup(update, ctx)
            elif data == "flash_clean_dup_exec":  await self.flash.flash_clean_dup_execute(update, ctx)
            elif data == "flash_clean_dead":      await self.flash.flash_clean_dead(update, ctx)
            elif data == "flash_clean_dead_exec": await self.flash.flash_clean_dead_execute(update, ctx)
            elif data == "flash_delay_fast":      await self.flash.flash_set_delay(update, ctx, 5, 10)
            elif data == "flash_delay_med":       await self.flash.flash_set_delay(update, ctx, 8, 20)
            elif data == "flash_delay_safe":      await self.flash.flash_set_delay(update, ctx, 15, 40)
            elif data == "flash_rest_30":         await self.flash.flash_set_rest(update, ctx, 30)
            elif data == "flash_rest_60":         await self.flash.flash_set_rest(update, ctx, 60)
            elif data == "flash_rest_120":        await self.flash.flash_set_rest(update, ctx, 120)
            elif data.startswith("flash_num_"):
                nid = int(data[len("flash_num_"):])
                await self.flash.flash_toggle_num(update, ctx, nid)
            elif data.startswith("flash_ad_del_exec_"):
                aid = int(data[len("flash_ad_del_exec_"):])
                await self.flash.flash_ad_del_execute(update, ctx, aid)
            elif data.startswith("flash_ad_del_"):
                aid = int(data[len("flash_ad_del_"):])
                await self.flash.flash_ad_del_confirm(update, ctx, aid)
            elif data.startswith("flash_ad_"):
                aid = int(data[len("flash_ad_"):])
                await self.flash.flash_toggle_ad(update, ctx, aid)

            else:
                await self.u.show_main(update, ctx)

        except Exception as e:
            logger.error(f"callback error [{data}]: {e}", exc_info=True)
            try:
                await q.message.reply_text(f"⚠️ خطأ داخلي: {type(e).__name__}")
            except Exception:
                pass
