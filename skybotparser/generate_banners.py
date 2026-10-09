from PIL import Image, ImageDraw, ImageFont
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

res_dir = os.path.join(BASE_DIR, "installer_res")
os.makedirs(res_dir, exist_ok=True)

# Загружаем шрифты Windows с полной поддержкой кириллицы
font_bold_title = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 34)
font_bold_med = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 20)
font_regular = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 18)
font_small_bold = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 14)

def draw_gradient_text(target_img, pos_x, pos_y, text, font, colors):
    """Отрисовывает текст с плавным многоцветным градиентом в цветах логотипа Авито."""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 8
    w = tw + pad * 2
    h = th + pad * 2

    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.text((pad - bbox[0], pad - bbox[1]), text, fill=255, font=font)

    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    n_seg = len(colors) - 1
    for x in range(w):
        t = x / max(1, w - 1)
        seg = min(int(t * n_seg), n_seg - 1)
        seg_t = (t - seg / n_seg) * n_seg
        c1, c2 = colors[seg], colors[seg + 1]
        r = int(c1[0] + (c2[0] - c1[0]) * seg_t)
        g = int(c1[1] + (c2[1] - c1[1]) * seg_t)
        b = int(c1[2] + (c2[2] - c1[2]) * seg_t)
        for y in range(h):
            grad.putpixel((x, y), (r, g, b, 255))

    grad.putalpha(mask)
    target_img.paste(grad, (pos_x - pad, pos_y - pad), grad)

# ==============================================================================
# 1. WizardImageFile (328 x 628 px - HiDPI 2x)
# ==============================================================================
W, H = 328, 628
banner = Image.new("RGB", (W, H), (15, 23, 42))  # #0f172a темный фон
draw = ImageDraw.Draw(banner)

# Мягкий градиент на фоне
for y in range(H):
    r = int(11 + (15 - 11) * (y / H))
    g = int(19 + (23 - 19) * (y / H))
    b = int(41 + (42 - 41) * (y / H))
    draw.line([(0, y), (W - 2, y)], fill=(r, g, b))

# Неоновая вертикальная линия справа
draw.line([(W - 1, 0), (W - 1, H)], fill=(2, 132, 199), width=2)

# Логотип по центру
cand_logo = os.path.join(PARENT_DIR, "Avito-Parser3", "skybase", "img", "skybase_icon_256.png")
logo_path = cand_logo if os.path.exists(cand_logo) else os.path.join(res_dir, "skybase_icon_256.png")
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA")
    logo = logo.resize((140, 140), Image.Resampling.LANCZOS)
    x_logo = (W - 140) // 2
    banner.paste(logo, (x_logo, 75), logo)

# Текст AvitoHunter в полутонах логотипа Авито (Зеленый -> Голубой -> Фиолетовый -> Коралловый)
avito_colors = [
    (4, 224, 97),    # #04E061 Зеленый Авито
    (0, 170, 255),   # #00AAFF Голубой Авито
    (167, 58, 253),  # #A73AFD Фиолетовый Авито
    (255, 97, 99)    # #FF6163 Кораллово-красный Авито
]

text_title = "AvitoHunter"
bbox_title = font_bold_title.getbbox(text_title)
w_title = bbox_title[2] - bbox_title[0]
draw_gradient_text(banner, (W - w_title) // 2, 245, text_title, font_bold_title, avito_colors)

# Текст подзаголовка: PARSER & BOT (Белый с мягким свечением)
text_sub = "PARSER & BOT"
bbox_sub = draw.textbbox((0, 0), text_sub, font=font_bold_med)
w_sub = bbox_sub[2] - bbox_sub[0]
draw.text(((W - w_sub) // 2, 295), text_sub, fill=(241, 245, 249), font=font_bold_med)

# Тонкая разделительная линия в цветах Авито
draw.line([(45, 345), (W - 45, 345)], fill=(30, 41, 59), width=2)
draw.line([(85, 345), (145, 345)], fill=(4, 224, 97), width=2)
draw.line([(145, 345), (205, 345)], fill=(0, 170, 255), width=2)
draw.line([(205, 345), (245, 345)], fill=(255, 97, 99), width=2)

# Подзаголовок: Мониторинг Avito
text_desc = "Мониторинг Avito"
bbox_desc = draw.textbbox((0, 0), text_desc, font=font_regular)
w_desc = bbox_desc[2] - bbox_desc[0]
draw.text(((W - w_desc) // 2, 375), text_desc, fill=(148, 163, 184), font=font_regular)

# Нижний текст версии
text_ver = "Версия 1.17"
bbox_ver = draw.textbbox((0, 0), text_ver, font=font_small_bold)
w_ver = bbox_ver[2] - bbox_ver[0]
draw.text(((W - w_ver) // 2, 575), text_ver, fill=(100, 116, 139), font=font_small_bold)

banner.save(os.path.join(res_dir, "wizard_large.bmp"), "BMP")
print("[+] wizard_large.bmp saved (328x628 HiDPI) with AvitoHunter multi-color branding")

# ==============================================================================
# 2. WizardSmallImageFile (110 x 116 px - HiDPI 2x)
# ==============================================================================
small_w, small_h = 110, 116
small = Image.new("RGB", (small_w, small_h), (15, 23, 42))
if os.path.exists(logo_path):
    s_logo = Image.open(logo_path).convert("RGBA")
    s_logo = s_logo.resize((84, 84), Image.Resampling.LANCZOS)
    small.paste(s_logo, ((small_w - 84) // 2, (small_h - 84) // 2), s_logo)

small.save(os.path.join(res_dir, "wizard_small.bmp"), "BMP")
print("[+] wizard_small.bmp saved (110x116 HiDPI)")
