(async function() {
  const host = window.location.hostname.toLowerCase();
  const items = [];

  // =================== 1. ALIEXPRESS ===================
  if (host.includes('ali') || host.includes('cainiao')) {
    const cards = Array.from(document.querySelectorAll('*')).filter(el => {
      const t = el.innerText || '';
      return /(\d{4}\s+\d{4}\s+\d{4}\s+\d{4})|№\s*(\d{14,20})|\b(\d{15,18})\b/.test(t) &&
             /СОЗДАН|В пути|Привез[её]м|Доставка|Оплачен|Получен/i.test(t) &&
             el.querySelector('img');
    });

    const uniqueCards = cards.filter(c => !cards.some(p => p !== c && p.contains(c)));

    uniqueCards.forEach(card => {
      const txt = card.innerText || '';
      if (txt.includes('ОДНА ЦЕНА') && !txt.includes('СОЗДАН')) return;

      const numMatch = txt.match(/(\d{4}\s+\d{4}\s+\d{4}\s+\d{4})|№\s*(\d{14,20})|\b(\d{15,18})\b/);
      const orderNum = numMatch ? (numMatch[1] || numMatch[2] || numMatch[3] || '').replace(/\s+/g, '') : '';
      if (!orderNum) return;

      const priceMatch = txt.match(/(\d+[,\.\s\d]*\s*₽)/);
      const price = priceMatch ? priceMatch[1] : '';

      let st = 'handover', stText = '📦 Создан (ожидает отправки)';
      if (/готов к выдаче|прибыл в пункт/i.test(txt)) { st = 'ready'; stText = '🟢 Готов к выдаче (ПВЗ)'; }
      else if (/в пути|доставляется|доставк/i.test(txt)) { st = 'in_delivery'; stText = '🚚 В пути'; }
      else if (/доставлен|получен/i.test(txt)) { st = 'delivered'; stText = '✅ Доставлен'; }

      // Ищем именно фото товара: отсекаем аватарки, иконки, логотипы
      const allImgs = Array.from(card.querySelectorAll('img')).concat(
        Array.from(document.querySelectorAll('img')).filter(im => {
          return card.contains(im);
        })
      );

      const validImgs = Array.from(new Set(allImgs)).filter(im => {
        const s = (im.currentSrc || im.getAttribute('src') || im.src || '').toLowerCase();
        if (!s || s.startsWith('data:image/svg') || s.includes('.svg')) return false;
        if (s.includes('avatar') || s.includes('logo') || s.includes('icon') || s.includes('loyalty') || 
            s.includes('user') || s.includes('profile') || s.includes('ae3bff64fedce4135b5415d9b4534f53dv')) {
          return false;
        }
        const w = im.naturalWidth || im.clientWidth || im.width || 0;
        const h = im.naturalHeight || im.clientHeight || im.height || 0;
        if (w > 0 && w < 30 && h > 0 && h < 30) return false;
        return true;
      });

      const prodImg = validImgs.find(im => {
        const s = (im.currentSrc || im.src || '').toLowerCase();
        return (s.includes('alicdn') || s.includes('ae01') || s.includes('/kf/') || s.includes('aliexpress-media')) &&
               !s.includes('ae3bff64fedce4135b5415d9b4534f53dv');
      }) || validImgs[0];

      let preview = prodImg ? (prodImg.currentSrc || prodImg.getAttribute('src') || prodImg.src) : '';
      if (!preview || preview.includes('Ae3bff64fedce4135b5415d9b4534f53dV')) {
        preview = 'img/orders/ali_' + orderNum + '.png';
      }

      let title = '';
      const link = card.querySelector('a[title]') || card.querySelector('a[href*="/item/"]');
      if (link) title = (link.getAttribute('title') || link.innerText || '').trim();
      if (!title || title.length < 4) {
        const lines = txt.split('\n').map(s => s.trim()).filter(s => s.length > 5);
        title = lines.find(l => !l.includes('₽') && !l.includes('СОЗДАН') && !l.includes('Привезём') && !l.includes('Доставка') && !l.includes('№') && !/^\d+$/.test(l)) || ('Товар AliExpress #' + orderNum.slice(-4));
      }

      items.push({
        name: title,
        price: price,
        preview: preview,
        order_number: orderNum,
        track_number: '',
        status: st,
        status_text: stText,
        shop: 'AliExpress',
        url: 'https://aliexpress.ru/order-list'
      });
    });
  }

  // =================== 2. OZON ===================
  else if (host.includes('ozon')) {
    const EXCLUDE_PICS = ['12209332501', '8329600329']; // Отменённые и полученные
    const allImgs = Array.from(document.querySelectorAll('img')).filter(im => {
      const s = (im.currentSrc || im.src || '').toLowerCase();
      return s.includes('ozone.ru') && s.includes('wc1200') && !s.includes('.svg') && !s.includes('logo');
    });

    const seen = new Set();

    allImgs.forEach((im, idx) => {
      const src = im.currentSrc || im.src || '';
      if (!src || seen.has(src) || EXCLUDE_PICS.some(id => src.includes(id))) return;

      let card = im.parentElement;
      for (let i = 0; i < 8 && card && card !== document.body; i++) {
        if (card.innerText && card.innerText.includes('₽')) break;
        card = card.parentElement;
      }

      const t = card ? card.innerText : '';
      const prMatch = t.match(/(\d[\d\s]*\s*₽)/);
      const price = prMatch ? prMatch[1].replace(/\s+/g, ' ') : '';

      let statusText = '🚚 В пути';
      let statusKey = 'in_delivery';

      if (/забирать|готов\s*к\s*выдаче/i.test(t) || src.includes('7055524407') || src.includes('10780668611')) {
        statusText = '🟢 Можно забирать';
        statusKey = 'ready';
      } else if (/в\s*службе\s*доставки/i.test(t) || src.includes('9490936126') || src.includes('7927968412') || src.includes('9964690262')) {
        statusText = '🚚 В службе доставки';
        statusKey = 'in_delivery';
      }

      const link = card ? card.querySelector('a[href*="/product/"]') : null;
      let title = link ? (link.getAttribute('title') || link.innerText || '').trim().split('\n')[0] : '';
      if (!title || title.length < 5 || title.includes('₽')) {
        const txts = Array.from((card || im.parentElement).querySelectorAll('span, a, div'))
          .map(e => (e.innerText || '').trim())
          .filter(x => x.length > 8 && x.length < 120 && !x.includes('₽') && !/пути|достав|заказ|ожидаем/i.test(x));
        title = txts[0] || ('Товар Ozon #' + (idx + 1));
      }

      seen.add(src);

      items.push({
        name: title,
        price: price,
        preview: src,
        order_number: 'OZ-' + src.split('/').pop().replace(/\D/g, '').slice(-8),
        status: statusKey,
        status_text: statusText,
        notes: 'Пункт Ozon: ул. Ленина, 365',
        shop: 'Ozon',
        url: link ? link.href : 'https://www.ozon.ru/my/orderlist/'
      });
    });
  } else {
    alert('⚠️ Пожалуйста, откройте страницу с заказами Ozon (ozon.ru/my/orderlist) или AliExpress (aliexpress.ru/order-list)!');
    return;
  }

  if (items.length === 0) {
    alert('⚠️ Активные заказы не обнаружены на текущей странице.');
    return;
  }

  console.log(`Найдено активных товаров: ${items.length}`);
  const payload = encodeURIComponent(JSON.stringify(items));
  window.open('http://localhost:8080/#import=' + payload, '_blank');
})();
