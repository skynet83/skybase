import math
from PIL import Image, ImageDraw, ImageFilter

def generate_restart_icon():
    base_glow = Image.open("img/server_btn_yellow_glow.png").convert("RGBA")
    w, h = base_glow.size # 128, 128
    
    scale = 8
    S = 128 * scale
    center = (S / 2.0, S / 2.0)
    
    # Полностью очищаем внутренний круг (радиус до 35 пикселей) от старого символа
    # Внутренний кружок в server_btn_yellow_glow имеет плавный темный градиент
    clean_base = base_glow.copy()
    draw_clean = ImageDraw.Draw(clean_base)
    
    cx, cy = 64, 64
    # Заполняем область от r=35 до r=0 плавным радиальным градиентом
    for r in range(35, 0, -1):
        # В центре (r=0) цвет ~38, на краю (r=35) цвет ~26
        factor = r / 35.0
        val = int(25 + (38 - 25) * (1 - factor))
        draw_clean.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(val, val, val, 255))
    
    # Сглаживаем маской
    mask = Image.new("L", (128, 128), 0)
    d_mask = ImageDraw.Draw(mask)
    d_mask.ellipse([cx - 33, cy - 33, cx + 33, cy + 33], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(3.0))
    
    clean_base = Image.composite(clean_base.filter(ImageFilter.GaussianBlur(1.0)), clean_base, mask)
    
    # Апскейл до 1024x1024
    hires_bg = clean_base.resize((S, S), Image.Resampling.LANCZOS)
    
    # Слой стрелок
    arrow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(arrow_layer)
    
    # Радиус стрелок (подогнан под размер символа питания в server_btn_on)
    # В server_btn_on круг символа питания имеет радиус ~16.5px, а верхняя палочка идет до r=21px
    radius = 17.5 * scale
    thickness = 2.4 * scale # толщина линии в точности как у знака питания
    
    box = [center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius]
    
    # Две полукруглые стрелки
    # Верхняя дуга: от 215° до 355°
    # Нижняя дуга: от 35° до 175°
    arc1_start = 215
    arc1_end = 352
    arc2_start = 35
    arc2_end = 172
    
    # Цветовая гамма neon-yellow (в тон кольца server_btn_yellow_glow)
    neon_glow = (245, 158, 11, 160)
    outer_edge = (217, 149, 12, 230)
    inner_core = (254, 240, 138, 255)
    highlight  = (255, 255, 220, 255)
    
    # 1. Свечение
    glow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d_glow = ImageDraw.Draw(glow_layer)
    d_glow.arc(box, start=arc1_start, end=arc1_end, fill=neon_glow, width=int(thickness * 2.8))
    d_glow.arc(box, start=arc2_start, end=arc2_end, fill=neon_glow, width=int(thickness * 2.8))
    
    # Наконечник стрелки
    def draw_arrow_head(draw_obj, angle_deg, fill_color, size_mult=1.0):
        rad = math.radians(angle_deg)
        # Точка на дуге
        ax = center[0] + radius * math.cos(rad)
        ay = center[1] + radius * math.sin(rad)
        
        # Касательная по часовой стрелке
        tx = -math.sin(rad)
        ty = math.cos(rad)
        # Нормаль наружу
        nx = math.cos(rad)
        ny = math.sin(rad)
        
        hlen = 6.2 * scale * size_mult
        hw   = 4.8 * scale * size_mult
        
        # Острие слегка вынесено вперед
        pt_tip = (ax + tx * (hlen * 0.45), ay + ty * (hlen * 0.45))
        pt_left = (ax - tx * (hlen * 0.55) + nx * hw, ay - ty * (hlen * 0.55) + ny * hw)
        pt_right = (ax - tx * (hlen * 0.55) - nx * hw, ay - ty * (hlen * 0.55) - ny * hw)
        
        draw_obj.polygon([pt_tip, pt_left, pt_right], fill=fill_color)

    draw_arrow_head(d_glow, arc1_end, neon_glow, size_mult=1.6)
    draw_arrow_head(d_glow, arc2_end, neon_glow, size_mult=1.6)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(2.0 * scale))
    
    # 2. Тело стрелки
    d.arc(box, start=arc1_start, end=arc1_end, fill=outer_edge, width=int(thickness))
    d.arc(box, start=arc2_start, end=arc2_end, fill=outer_edge, width=int(thickness))
    
    d.arc(box, start=arc1_start + 1, end=arc1_end - 1, fill=inner_core, width=int(thickness * 0.65))
    d.arc(box, start=arc2_start + 1, end=arc2_end - 1, fill=inner_core, width=int(thickness * 0.65))
    
    draw_arrow_head(d, arc1_end, outer_edge, size_mult=1.1)
    draw_arrow_head(d, arc2_end, outer_edge, size_mult=1.1)
    
    draw_arrow_head(d, arc1_end, inner_core, size_mult=0.85)
    draw_arrow_head(d, arc2_end, inner_core, size_mult=0.85)
    
    # Сборка
    result = hires_bg.copy()
    result.alpha_composite(glow_layer)
    result.alpha_composite(arrow_layer)
    
    # Даунскейлинг обратно в 128x128
    final_icon = result.resize((128, 128), Image.Resampling.LANCZOS)
    final_icon.save("img/server_btn_restart_styled.png", "PNG")
    print("[OK] Обновлен img/server_btn_restart_styled.png")

if __name__ == "__main__":
    generate_restart_icon()
