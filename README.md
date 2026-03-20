# Muharram Bot v4.0

## 🚀 التشغيل السريع
```bash
pip install -r requirements.txt
python main.py
```

## 📁 هيكل المجلدات الجديد vs القديم

### الهيكل القديم (v3)
```
Muharram/
├── main.py
├── config.py                    ← إعدادات مكثوفة
├── requirements.txt
├── database/
│   └── db_handler.py            ← قاعدة البيانات
├── handlers/                    ← كل المعالجات مختلطة
│   ├── admin_handlers.py        ← 1286 سطر
│   ├── user_handlers.py         ← 1367 سطر (نشر + أرقام + مجلدات + جلب)
│   ├── callback_handlers.py     ← 425 سطر
│   ├── flash_handler.py         ← 780 سطر
│   ├── engineer_handler.py      ← 550 سطر
│   ├── control_handler.py       ← 205 سطر
│   ├── session_manager.py       ← 226 سطر
│   └── video_handler.py         ← 185 سطر
├── services/                    ← كل الخدمات مختلطة
│   ├── publish_service.py
│   ├── folder_service.py
│   ├── fetch_service.py
│   ├── auth_service.py
│   ├── engineer_service.py
│   ├── video_service.py
│   └── ad_protector.py
└── utils/
    ├── helpers.py
    ├── logger.py
    └── encryption_tools.py
```

### الهيكل الجديد (v4) ← كل نظام في مجلده الخاص
```
Muharram_v4/
├── main.py                      ← نقطة دخول نظيفة
├── requirements.txt
├── config/
│   └── settings.py              ← كل الإعدادات موثقة ومرتبة
├── database/
│   └── db_handler.py            ← قاعدة البيانات
├── utils/
│   ├── helpers.py
│   ├── logger.py
│   └── encryption_tools.py
├── systems/                     ← كل نظام مستقل بذاته
│   ├── publish/                 ← نظام النشر
│   │   ├── service.py           ← منطق النشر
│   │   └── handler.py           ← معالج أزرار المستخدم
│   ├── folder/                  ← نظام المجلدات
│   │   └── service.py
│   ├── fetch/                   ← نظام جلب الروابط
│   │   └── service.py
│   ├── flash/                   ← محرك Turbo
│   │   └── handler.py           ← (يشمل الـ engine والـ handler)
│   ├── engineer/                ← نظام المهندس الذكي
│   │   ├── service.py
│   │   └── handler.py
│   ├── session/                 ← إدارة الجلسات والتسجيل
│   │   ├── auth.py              ← تسجيل الدخول بالرقم
│   │   └── manager.py           ← نقل الاشتراك وإلغاؤه
│   ├── video/                   ← الفيديوهات التعليمية
│   │   ├── service.py
│   │   └── handler.py
│   └── protection/              ← حماية وتشفير الإعلانات
│       └── ad_protector.py
├── bot/                         ← طبقة البوت (تيليجرام)
│   ├── handlers/
│   │   ├── admin.py             ← لوحة الأدمن كاملة
│   │   └── control.py           ← مفاتيح تحكم الأنظمة
│   └── callbacks/
│       └── router.py            ← موزع الضغطات (callback router)
├── logs/                        ← ملفات اللوج
├── temp/                        ← ملفات مؤقتة
└── exports/                     ← ملفات التصدير
```

## 🔑 ملف config/settings.py
غيّر هذه القيم قبل التشغيل:
- `BOT_TOKEN` — توكين البوت من BotFather
- `API_ID` و `API_HASH` — من my.telegram.org
- `ADMIN_IDS` — قائمة ID الأدمن
- `ENCRYPTION_KEY` — مفتاح تشفير الجلسات

## 💡 أفكار التطوير المقترحة

### ✅ تحسينات فورية (يجب تطبيقها)
1. **Unique Hash per message** — كل رسالة تشفير مختلف → يتجنب اكتشاف البوتات
2. **حد يومي للنشر** — 80 رسالة/يوم/رقم كحد أقصى تلقائي
3. **خوارزمية موجات الانضمام** — 5 مجموعات ثم استراحة بدل الانضمام المتواصل
4. **زر نشر سريع** — يعيد آخر إعداد دون إعادة الضبط

### 🔄 تحسينات متوسطة
5. **جدولة النشر** — نشر تلقائي بوقت محدد
6. **تدوير الإعلانات** — تغيير نص الإعلان كل N رسالة
7. **تقرير يومي للأدمن** — ملخص تلقائي كل صباح
8. **فلترة الروابط قبل الانضمام** — فحص مسبق لتجنب المجموعات الفارغة

### 🛡️ أمان الأرقام
9. **تدوير بصمة الجهاز** — تغيير device_model أسبوعياً
10. **Gaussian delay** — فاصل عشوائي يبدو بشرياً بدل uniform
11. **نظام يوم راحة** — كل رقم يستريح يومين أسبوعياً

### 🔐 تحسين التشفير
12. **Unicode Variants** — استخدام ترميزات مختلفة للحروف العربية
13. **تدوير أسلوب إخفاء الرقم** — 4 أساليب مختلفة بشكل عشوائي
14. **إيموجي عشوائية** — hash مختلف لكل رسالة

### ✨ ميزات جديدة
15. **مساعد ذكي "ماذا أفعل؟"** — تحليل الوضع واقتراح الخطوة التالية
16. **قائمة المجموعات الموثوقة** — Whitelist للمجموعات الناجحة
17. **تنبيهات الصحة الاستباقية** — تحذير قبل أن يُحظر الرقم
