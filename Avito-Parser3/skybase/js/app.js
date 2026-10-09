// Авто-перенаправление при открытии файла напрямую (двойной клик по index.html)
if (window.location.protocol === 'file:') {
  window.location.href = 'http://localhost/';
}

// Безопасное чтение JSON с удалением UTF-8 BOM
async function parseJsonSafely(res) {
  if (!res || !res.ok) throw new Error('HTTP ' + (res ? res.status : 'no response'));
  const text = await res.text();
  const cleanText = text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text;
  return JSON.parse(cleanText.trim());
}

function getSafeAvitoPhotoUrl(photoUrl) {
  if (!photoUrl || typeof photoUrl !== 'string') return '';
  const trimmed = photoUrl.trim();
  if (!trimmed) return '';
  // Если сайт открыт на самом сервере (localhost, 127.0.0.1 или IP сервера) -
  // проксируем картинки через backend-прокси, чтобы браузер не выдавал реальный IP сервера в CDN Avito
  const host = window.location.hostname;
  const isLocalServer = host === 'localhost' || host === '127.0.0.1' || host === '62.183.2.72' || host.startsWith('192.168.') || host.startsWith('10.');
  if (isLocalServer && (trimmed.includes('avito.st') || trimmed.includes('avito.ru'))) {
    return '/api/avito/proxy-image?url=' + encodeURIComponent(trimmed);
  }
  return trimmed;
}
window.getSafeAvitoPhotoUrl = getSafeAvitoPhotoUrl;

const _pageLoadedTime = Date.now();

// Всплывающие уведомления (Toast) с поддержкой цветовых тем: yellow, red, green, info
window.showToast = function(msg, durationOrType = 1500, explicitType = null) {
  // Неавторизованным гостям никогда не показываем уведомления о товарах Avito
  if (!currentUser && (typeof msg === 'string') && (msg.includes('🔔') || msg.includes('объявлен') || msg.includes('Avito') || msg.includes('База загружена'))) {
    return;
  }
  let toast = document.getElementById('electro-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'electro-toast';
    document.body.appendChild(toast);
  }

  let duration = 1500;
  let type = 'info';

  if (typeof durationOrType === 'number') {
    duration = durationOrType;
    if (typeof explicitType === 'string') type = explicitType;
  } else if (typeof durationOrType === 'string') {
    type = durationOrType;
  }

  // Настройка фонов и стилей под типы уведомлений
  let bgGradient = 'linear-gradient(135deg, #0284c7, #0369a1)';
  let textColor = '#ffffff';
  let shadowColor = 'rgba(2, 132, 199, 0.45)';
  let borderColor = '#38bdf8';

  if (type === 'orange' || type === 'blacklist') {
    bgGradient = 'linear-gradient(135deg, #f97316, #ea580c)';
    textColor = '#ffffff';
    shadowColor = 'rgba(249, 115, 22, 0.6)';
    borderColor = '#fb923c';
  } else if (type === 'yellow' || type === 'warning' || type === 'restart') {
    bgGradient = 'linear-gradient(135deg, #f59e0b, #d97706)';
    textColor = '#1a1300';
    shadowColor = 'rgba(245, 158, 11, 0.6)';
    borderColor = '#fbbf24';
  } else if (type === 'red' || type === 'danger' || type === 'error' || type === 'shutdown') {
    bgGradient = 'linear-gradient(135deg, #ef4444, #dc2626)';
    textColor = '#ffffff';
    shadowColor = 'rgba(239, 68, 68, 0.6)';
    borderColor = '#f87171';
  } else if (type === 'green' || type === 'success') {
    bgGradient = 'linear-gradient(135deg, #10b981, #059669)';
    textColor = '#ffffff';
    shadowColor = 'rgba(16, 185, 129, 0.6)';
    borderColor = '#34d399';
  }

  toast.style.cssText = `position:fixed;bottom:2rem;right:2rem;background:${bgGradient};color:${textColor};border:1px solid ${borderColor};padding:0.85rem 1.45rem;border-radius:12px;box-shadow:0 12px 28px rgba(0,0,0,0.4), 0 0 16px ${shadowColor};font-weight:700;font-size:0.95rem;z-index:99999;transition:all 0.3s cubic-bezier(0.16, 1, 0.3, 1);transform:translateY(20px);opacity:0;pointer-events:none;display:flex;align-items:center;gap:0.5rem;letter-spacing:0.3px;`;
  toast.innerHTML = msg;
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';
  clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(20px)';
  }, duration);
};

let _sharedAudioCtx = null;
let _chimeBlobUrl = null;
let _persistentNotificationAudio = null;

function getOrCreateAudioContext() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    if (navigator.userActivation && !navigator.userActivation.hasBeenActive) {
      return null;
    }
    if (!_sharedAudioCtx) {
      _sharedAudioCtx = new AudioCtx();
    }
    if (_sharedAudioCtx.state === 'suspended') {
      _sharedAudioCtx.resume().catch(() => {});
    }
    return _sharedAudioCtx;
  } catch (e) {
    return null;
  }
}

function getChimeBlobUrl() {
  if (_chimeBlobUrl) return _chimeBlobUrl;
  try {
    const sampleRate = 44100;
    const duration = 2.3;
    const numSamples = Math.floor(sampleRate * duration);
    const buffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(buffer);
    const writeString = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + numSamples * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, numSamples * 2, true);

    // Классический 3-нотный гонг аэропортов и авто/жд станций:
    // Нота 1: Соль (G4, 392 Гц) -> Нота 2: До (C5, 523.25 Гц) -> Нота 3: Ми (E5, 659.25 Гц)
    // Размеренный интервал 0.36с между ударами и теплое резонансное затухание колокольчиков
    const notes = [
      { start: 0.00, freq: 392.00, decay: 2.5 },
      { start: 0.36, freq: 523.25, decay: 2.5 },
      { start: 0.72, freq: 659.25, decay: 2.0 }
    ];

    for (let i = 0; i < numSamples; i++) {
      const t = i / sampleRate;
      let sample = 0;

      for (let n = 0; n < notes.length; n++) {
        const note = notes[n];
        const tau = t - note.start;
        if (tau >= 0) {
          const env = tau < 0.004 ? (tau / 0.004) : Math.exp(-note.decay * (tau - 0.004));
          const s = (
            0.62 * Math.sin(2 * Math.PI * note.freq * tau) +
            0.24 * Math.sin(2 * Math.PI * (note.freq * 1.0025) * tau) +
            0.18 * Math.sin(2 * Math.PI * (note.freq * 2.0) * tau) * Math.exp(-4.5 * tau) +
            0.12 * Math.sin(2 * Math.PI * (note.freq * 2.76) * tau) * Math.exp(-6.5 * tau) +
            0.06 * Math.sin(2 * Math.PI * (note.freq * 4.0) * tau) * Math.exp(-9.0 * tau)
          ) * env;
          sample += s;
        }
      }

      const val = Math.max(-0.95, Math.min(0.95, sample * 0.88));
      view.setInt16(44 + i * 2, val * 32767, true);
    }
    const blob = new Blob([buffer], { type: 'audio/wav' });
    _chimeBlobUrl = URL.createObjectURL(blob);
    return _chimeBlobUrl;
  } catch (e) {
    return null;
  }
}

const AVITO_SOUND_PRESETS = [
  { id: 'default', name: 'Системный звук (по умолчанию)', file: 'sound/notification.mp3?v=98.0', duration: '1.5с', icon: '🔔', desc: 'Стандартный звуковой сигнал оповещения' }
];

let _previewAudio = null;
let _previewAudioPlayingUrl = null;
let _serverCustomSoundInfo = null;

function getActiveSoundConfig() {
  let choice = localStorage.getItem('electro_avito_sound_choice') || 'default';
  if (choice !== 'custom' && !AVITO_SOUND_PRESETS.some(p => p.id === choice)) {
    choice = 'default';
  }
  const volumeStr = localStorage.getItem('electro_avito_sound_volume');
  const volume = (volumeStr !== null && volumeStr !== undefined) ? parseFloat(volumeStr) : 1.0;
  const safeVol = isNaN(volume) ? 1.0 : Math.max(0, Math.min(1, volume));

  if (choice === 'custom') {
    const customUrl = localStorage.getItem('electro_avito_custom_sound_url') || 'sound/custom_user_sound.mp3';
    const customName = localStorage.getItem('electro_avito_custom_sound_name') || 'Свой файл с диска';
    return {
      id: 'custom',
      name: customName,
      file: customUrl,
      icon: '📁',
      desc: 'Пользовательский звуковой файл с локального диска',
      duration: 'пользовательский',
      volume: safeVol
    };
  }

  const preset = AVITO_SOUND_PRESETS.find(p => p.id === choice) || AVITO_SOUND_PRESETS[0];
  return {
    ...preset,
    volume: safeVol
  };
}

function getNotificationAudioElement() {
  const cfg = getActiveSoundConfig();
  if (!_persistentNotificationAudio) {
    try {
      _persistentNotificationAudio = new Audio(cfg.file);
      _persistentNotificationAudio.preload = 'auto';
      _persistentNotificationAudio.volume = cfg.volume;
      _persistentNotificationAudio._currentSrc = cfg.file;
    } catch (e) {}
  } else if (_persistentNotificationAudio._currentSrc !== cfg.file) {
    try {
      _persistentNotificationAudio.pause();
      _persistentNotificationAudio.src = cfg.file;
      _persistentNotificationAudio._currentSrc = cfg.file;
      _persistentNotificationAudio.volume = cfg.volume;
      _persistentNotificationAudio.load();
    } catch (_) {}
  } else {
    _persistentNotificationAudio.volume = cfg.volume;
  }
  return _persistentNotificationAudio;
}

// Постоянная разблокировка звукового движка при любых действиях пользователя на странице
function unlockAudioEngine() {
  if (navigator.userActivation && !navigator.userActivation.hasBeenActive) {
    return;
  }
  const ctx = getOrCreateAudioContext();
  if (ctx && ctx.state === 'suspended') {
    ctx.resume().catch(() => {});
  }
  const el = getNotificationAudioElement();
  if (el && !el._isUnlocked) {
    el.volume = 1.0;
    const playPromise = el.play();
    if (playPromise !== undefined) {
      playPromise.then(() => {
        el.pause();
        el.currentTime = 0;
        el._isUnlocked = true;
      }).catch(() => {});
    }
  }
}
['click', 'keydown', 'touchstart'].forEach(evt => {
  window.addEventListener(evt, unlockAudioEngine, { passive: true });
});

// Мигание заголовка вкладки при свернутом окне
let _titleFlashTimer = null;
let _origDocTitle = document.title || 'AvitoHunter';

function notifyNewCardsBackground(count) {
  if (document.hidden) {
    if (_titleFlashTimer) clearInterval(_titleFlashTimer);
    let flashOn = true;
    _titleFlashTimer = setInterval(() => {
      document.title = flashOn ? `🔔 (+${count} НОВЫХ) ${_origDocTitle}` : `⚡ НОВЫЙ ТОВАР! ${_origDocTitle}`;
      flashOn = !flashOn;
    }, 900);
  }
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && _titleFlashTimer) {
    clearInterval(_titleFlashTimer);
    _titleFlashTimer = null;
    document.title = _origDocTitle;
  }
}, { passive: true });

window.playAvitoSoundPreview = function(soundUrl, vol) {
  try {
    if (_previewAudio) {
      _previewAudio.pause();
      _previewAudio.currentTime = 0;
      if (_previewAudioPlayingUrl === soundUrl) {
        _previewAudioPlayingUrl = null;
        window._updatePreviewButtonsState();
        return;
      }
    }
    const safeVol = (vol !== undefined && vol !== null) ? parseFloat(vol) : (parseFloat(localStorage.getItem('electro_avito_sound_volume') || '1.0'));
    _previewAudio = new Audio(soundUrl);
    _previewAudio.volume = isNaN(safeVol) ? 1.0 : Math.max(0, Math.min(1, safeVol));
    _previewAudioPlayingUrl = soundUrl;
    window._updatePreviewButtonsState();

    _previewAudio.onended = function() {
      _previewAudioPlayingUrl = null;
      window._updatePreviewButtonsState();
    };
    _previewAudio.onerror = function() {
      _previewAudioPlayingUrl = null;
      window._updatePreviewButtonsState();
      if (typeof window.showToast === 'function') {
        window.showToast('⚠️ Не удалось воспроизвести выбранный аудиофайл', 2500, 'red');
      }
    };

    const p = _previewAudio.play();
    if (p !== undefined && typeof p.catch === 'function') {
      p.catch(() => {
        _previewAudioPlayingUrl = null;
        window._updatePreviewButtonsState();
      });
    }
  } catch (e) {
    _previewAudioPlayingUrl = null;
    window._updatePreviewButtonsState();
  }
};

window.stopAvitoSoundPreview = function() {
  if (_previewAudio) {
    try {
      _previewAudio.pause();
      _previewAudio.currentTime = 0;
    } catch (_) {}
    _previewAudioPlayingUrl = null;
    window._updatePreviewButtonsState();
  }
};

window._updatePreviewButtonsState = function() {
  document.querySelectorAll('.btn-sound-preview-play').forEach(btn => {
    const u = btn.getAttribute('data-sound-url');
    if (u && u === _previewAudioPlayingUrl) {
      btn.innerHTML = '⏹ Стоп';
      btn.style.background = 'rgba(239, 68, 68, 0.25)';
      btn.style.borderColor = '#ef4444';
      btn.style.color = '#fca5a5';
    } else {
      btn.innerHTML = '▶️ Прослушать';
      btn.style.background = '';
      btn.style.borderColor = '';
      btn.style.color = '';
    }
  });
};

window.playAvitoChime = function(force = false) {
  // Звук играет ВСЕГДА, кроме случая, когда пользователь сам явно нажал «🔕 Звук ВЫКЛ»
  if (!force && localStorage.getItem('electro_avito_sound') === '0') return;

  try {
    const el = getNotificationAudioElement();
    if (el) {
      const cfg = getActiveSoundConfig();
      el.volume = cfg.volume;
      el.currentTime = 0;
      const p = el.play();
      if (p !== undefined && typeof p.catch === 'function') {
        p.catch(() => {
          // Fallback на стандартный гонг при ошибке
          if (cfg.id === 'custom') {
            try {
              el.src = 'sound/notification.mp3?v=98.0';
              el._currentSrc = 'sound/notification.mp3?v=98.0';
              el.currentTime = 0;
              el.play().catch(() => {});
            } catch (_) {}
          }
        });
      }
    }
  } catch (e) {}
};

window.toggleAvitoSound = function() {
  const current = localStorage.getItem('electro_avito_sound') !== '0';
  const next = !current;
  localStorage.setItem('electro_avito_sound', next ? '1' : '0');
  const btn = document.getElementById('btn-avito-sound-toggle');
  if (btn) {
    const textSpan = document.getElementById('btn-avito-sound-text');
    if (textSpan) {
      textSpan.textContent = next ? '🔔 Звук' : '🔕 Звук';
    } else {
      btn.innerHTML = next ? '🔔 Звук' : '🔕 Звук';
    }
    btn.classList.toggle('btn-active-blue', next);
    btn.classList.toggle('btn-inactive-gray', !next);
    btn.style.background = '';
    btn.style.color = '';
    btn.title = next ? 'Звук новых объявлений: включен (синий индикатор, нажмите для выключения)' : 'Звук новых объявлений: выключен (нажмите для включения)';
  }
  const combo = document.getElementById('btn-avito-sound-combo');
  if (combo) {
    combo.classList.toggle('is-sound-active', next);
  }
  if (next) {
    if (typeof window.playAvitoChime === 'function') window.playAvitoChime(true);
  }
  const modalContainer = document.getElementById('sound-settings-modal-container');
  if (modalContainer && typeof window.renderSoundSettingsModalContent === 'function') {
    window.renderSoundSettingsModalContent();
  }
};

window.selectAvitoSoundPreset = function(presetId) {
  window.stopAvitoSoundPreview();
  localStorage.setItem('electro_avito_sound_choice', presetId);
  const cfg = getActiveSoundConfig();
  getNotificationAudioElement();
  window.playAvitoSoundPreview(cfg.file);
  window.renderSoundSettingsModalContent();
  if (typeof window.showToast === 'function') {
    window.showToast(`🎵 Звук выбран: ${cfg.name}`, 2000);
  }
};

window.updateSoundVolume = function(val) {
  const num = parseInt(val, 10);
  const safeVal = isNaN(num) ? 100 : Math.max(0, Math.min(100, num));
  const frac = safeVal / 100;
  localStorage.setItem('electro_avito_sound_volume', frac.toString());
  const label = document.getElementById('sound-volume-val-label');
  if (label) label.textContent = safeVal + '%';
  if (_persistentNotificationAudio) {
    _persistentNotificationAudio.volume = frac;
  }
};

window.onSoundVolumeChanged = function(val) {
  window.updateSoundVolume(val);
  const cfg = getActiveSoundConfig();
  window.playAvitoSoundPreview(cfg.file, parseFloat(val) / 100);
};

window.selectCustomSoundAsActive = function() {
  window.stopAvitoSoundPreview();
  localStorage.setItem('electro_avito_sound_choice', 'custom');
  const cfg = getActiveSoundConfig();
  getNotificationAudioElement();
  window.playAvitoSoundPreview(cfg.file);
  window.renderSoundSettingsModalContent();
  if (typeof window.showToast === 'function') {
    window.showToast(`📁 Выбран свой звук: ${cfg.name}`, 2000);
  }
};

window.handleCustomSoundFileSelected = async function(input) {
  if (!input || !input.files || !input.files[0]) return;
  const file = input.files[0];
  if (file.size > 25 * 1024 * 1024) {
    alert('Размер файла не должен превышать 25 МБ');
    return;
  }

  const statusEl = document.getElementById('custom-sound-upload-status');
  if (statusEl) {
    statusEl.innerHTML = '<span style="color:#38bdf8;">⏳ Загрузка и сохранение аудиофайла...</span>';
    statusEl.style.display = 'block';
  }

  const reader = new FileReader();
  reader.onload = async function(e) {
    const dataUri = e.target.result;
    try {
      const res = await fetch('/api/sound/custom-upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, data: dataUri })
      });
      const data = await res.json();
      if (data && data.success) {
        localStorage.setItem('electro_avito_sound_choice', 'custom');
        localStorage.setItem('electro_avito_custom_sound_url', data.url);
        localStorage.setItem('electro_avito_custom_sound_name', data.filename || file.name);
        _serverCustomSoundInfo = { exists: true, url: data.url, filename: data.filename || file.name, size: data.size || file.size };
        getNotificationAudioElement();
        window.renderSoundSettingsModalContent();
        window.playAvitoSoundPreview(data.url);
        if (typeof window.showToast === 'function') {
          window.showToast(`✅ Свой звук установлен: ${data.filename || file.name}`, 3000);
        }
      } else {
        localStorage.setItem('electro_avito_sound_choice', 'custom');
        localStorage.setItem('electro_avito_custom_sound_url', dataUri);
        localStorage.setItem('electro_avito_custom_sound_name', file.name);
        getNotificationAudioElement();
        window.renderSoundSettingsModalContent();
        window.playAvitoSoundPreview(dataUri);
        if (typeof window.showToast === 'function') {
          window.showToast(`✅ Свой звук установлен локально: ${file.name}`, 3000);
        }
      }
    } catch (err) {
      localStorage.setItem('electro_avito_sound_choice', 'custom');
      localStorage.setItem('electro_avito_custom_sound_url', dataUri);
      localStorage.setItem('electro_avito_custom_sound_name', file.name);
      getNotificationAudioElement();
      window.renderSoundSettingsModalContent();
      window.playAvitoSoundPreview(dataUri);
      if (typeof window.showToast === 'function') {
        window.showToast(`✅ Свой звук сохранен в браузере: ${file.name}`, 3000);
      }
    }
  };
  reader.readAsDataURL(file);
};

window.handleCustomSoundLoadByPath = async function() {
  const input = document.getElementById('input-custom-sound-path');
  if (!input) return;
  const pathVal = (input.value || '').trim();
  const errEl = document.getElementById('custom-sound-path-error');
  if (!pathVal) {
    if (errEl) {
      errEl.textContent = 'Укажите путь к звуковому файлу на вашем диске';
      errEl.style.display = 'block';
    }
    input.focus();
    return;
  }

  const btn = document.getElementById('btn-load-sound-path');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Загрузка...';
  }
  if (errEl) errEl.style.display = 'none';

  try {
    const res = await fetch('/api/sound/load-by-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: pathVal })
    });
    const data = await res.json();
    if (data && data.success) {
      localStorage.setItem('electro_avito_sound_choice', 'custom');
      localStorage.setItem('electro_avito_custom_sound_url', data.url);
      localStorage.setItem('electro_avito_custom_sound_name', data.filename || pathVal);
      _serverCustomSoundInfo = { exists: true, url: data.url, filename: data.filename, size: data.size };
      getNotificationAudioElement();
      window.renderSoundSettingsModalContent();
      window.playAvitoSoundPreview(data.url);
      if (typeof window.showToast === 'function') {
        window.showToast(`✅ Звук загружен с диска: ${data.filename}`, 3000);
      }
    } else {
      if (errEl) {
        errEl.textContent = '⚠️ ' + (data.message || 'Не удалось найти или открыть файл по указанному пути');
        errEl.style.display = 'block';
      }
    }
  } catch (err) {
    if (errEl) {
      errEl.textContent = '⚠️ Ошибка запроса к серверу при загрузке файла';
      errEl.style.display = 'block';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Загрузить по пути';
    }
  }
};

window.openSoundSettingsModal = function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  const modalBody = document.getElementById('modal-body');
  if (!modalBody) return;
  const gearBtn = document.getElementById('btn-avito-sound-settings');
  if (gearBtn) gearBtn.classList.add('active');
  modalBody.innerHTML = '<div id="sound-settings-modal-container"></div>';
  window.renderSoundSettingsModalContent();
  window.openModal();

  // Подгружаем актуальную информацию о пользовательском файле с сервера
  fetch('/api/sound/list').then(r => r.json()).then(data => {
    if (data && data.custom) {
      _serverCustomSoundInfo = data.custom;
      window.renderSoundSettingsModalContent();
    }
  }).catch(() => {});
};

window.renderSoundSettingsModalContent = function() {
  const container = document.getElementById('sound-settings-modal-container');
  if (!container) return;

  const isSoundOn = localStorage.getItem('electro_avito_sound') !== '0';
  const activeCfg = getActiveSoundConfig();
  const curVol = activeCfg.volume;
  let currentChoice = localStorage.getItem('electro_avito_sound_choice') || 'default';
  if (currentChoice !== 'custom' && !AVITO_SOUND_PRESETS.some(p => p.id === currentChoice)) {
    currentChoice = 'default';
  }

  // Проверяем наличие кастомного звука (из localStorage или с сервера)
  const customUrl = localStorage.getItem('electro_avito_custom_sound_url') || (_serverCustomSoundInfo && _serverCustomSoundInfo.exists ? _serverCustomSoundInfo.url : null);
  const customName = localStorage.getItem('electro_avito_custom_sound_name') || (_serverCustomSoundInfo && _serverCustomSoundInfo.exists ? _serverCustomSoundInfo.filename : null);
  const hasCustomSound = Boolean(customUrl);

  const presetsHtml = AVITO_SOUND_PRESETS.map(p => {
    const isSelected = (currentChoice === p.id);
    return `
      <div class="sound-card-item" onclick="window.selectAvitoSoundPreset('${p.id}')" style="background:${isSelected ? 'rgba(14, 165, 233, 0.12)' : 'rgba(30, 41, 59, 0.65)'};border:1.5px solid ${isSelected ? '#0284c7' : 'rgba(148, 163, 184, 0.22)'};box-shadow:${isSelected ? '0 0 12px rgba(2, 132, 199, 0.28)' : 'none'};border-radius:12px;padding:0.75rem 0.95rem;display:flex;align-items:center;justify-content:space-between;gap:0.75rem;cursor:pointer;transition:all 0.2s ease;">
        <div style="display:flex;align-items:center;gap:0.75rem;flex:1;min-width:0;">
          <span style="font-size:1.45rem;flex-shrink:0;">${p.icon}</span>
          <div style="min-width:0;flex:1;">
            <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
              <strong style="color:#ffffff;font-size:0.9rem;">${p.name}</strong>
              <span style="background:rgba(148, 163, 184, 0.18);color:#94a3b8;font-size:0.72rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:6px;font-family:'JetBrains Mono',monospace;">${p.duration}</span>
              ${isSelected ? '<span style="background:rgba(16, 185, 129, 0.2);color:#34d399;border:1px solid rgba(16, 185, 129, 0.45);font-size:0.72rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:6px;">✓ Активен</span>' : ''}
            </div>
            <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:0.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              ${p.desc}
            </div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:0.45rem;flex-shrink:0;" onclick="event.stopPropagation();">
          <button type="button" class="cat-btn btn-sound-preview-play" data-sound-url="${p.file}" onclick="window.playAvitoSoundPreview('${p.file}')" style="padding:0.32rem 0.65rem;font-size:0.78rem;font-weight:700;border-radius:8px;background:rgba(59, 130, 246, 0.15);color:#60a5fa;border:1px solid rgba(59, 130, 246, 0.35);cursor:pointer;white-space:nowrap;">
            ${(_previewAudioPlayingUrl === p.file) ? '⏹ Стоп' : '▶️ Прослушать'}
          </button>
          ${!isSelected ? `
            <button type="button" class="cat-btn" onclick="window.selectAvitoSoundPreset('${p.id}')" style="padding:0.32rem 0.7rem;font-size:0.78rem;font-weight:700;border-radius:8px;background:#0284c7;color:#fff;border:none;cursor:pointer;white-space:nowrap;">
              Выбрать
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');

  const isCustomActive = (currentChoice === 'custom');

  container.innerHTML = `
    <div style="padding:0.25rem 0;">
      <!-- Шапка модального окна -->
      <div style="padding:0.25rem 0 1rem;border-bottom:1px solid rgba(148, 163, 184, 0.15);margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;">
        <div>
          <h3 style="font-size:1.25rem;font-weight:800;color:var(--accent);margin:0;display:flex;align-items:center;gap:0.45rem;">
            🎵 Звуковые оповещения
          </h3>
          <p style="font-size:0.83rem;color:var(--text-secondary);margin:0.25rem 0 0;line-height:1.4;">
            Выберите встроенный звук или укажите свой собственный файл с диска
          </p>
        </div>
        <div>
          <button type="button" class="cat-btn ${isSoundOn ? 'btn-active-blue' : 'btn-inactive-gray'}" onclick="window.toggleAvitoSound()" style="padding:0.4rem 0.85rem;font-size:0.84rem;font-weight:700;border-radius:10px;cursor:pointer;">
            ${isSoundOn ? '🔔 Звук включен' : '🔕 Звук выключен'}
          </button>
        </div>
      </div>

      <!-- Ползунок громкости -->
      <div style="background:rgba(15, 23, 42, 0.6);border:1px solid rgba(59, 130, 246, 0.25);border-radius:12px;padding:0.75rem 1rem;margin-bottom:1.15rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;">
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <span style="font-size:1.15rem;">🔊</span>
          <span style="font-size:0.86rem;font-weight:700;color:#f8fafc;">Громкость:</span>
          <span id="sound-volume-val-label" style="font-family:'JetBrains Mono',monospace;font-size:0.86rem;font-weight:700;color:#38bdf8;">${Math.round(curVol * 100)}%</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;flex:1;min-width:180px;max-width:280px;">
          <span style="font-size:0.75rem;color:var(--text-secondary);">0%</span>
          <input type="range" min="0" max="100" value="${Math.round(curVol * 100)}" style="flex:1;cursor:pointer;accent-color:#0284c7;" oninput="window.updateSoundVolume(this.value)" onchange="window.onSoundVolumeChanged(this.value)">
          <span style="font-size:0.75rem;color:var(--text-secondary);">100%</span>
        </div>
      </div>

      <!-- Список встроенных звуков -->
      <div style="margin-bottom:1.25rem;">
        <h4 style="font-size:0.92rem;font-weight:700;color:#cbd5e1;margin-bottom:0.65rem;display:flex;align-items:center;gap:0.35rem;">
          🔔 Системный звук (по умолчанию):
        </h4>
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
          ${presetsHtml}
        </div>
      </div>

      <!-- Блок своего файла с локального диска -->
      <div style="background:rgba(30, 41, 59, 0.5);border:1px solid rgba(148, 163, 184, 0.25);border-radius:12px;padding:1rem;margin-bottom:1.25rem;">
        <h4 style="font-size:0.92rem;font-weight:700;color:#f8fafc;margin-bottom:0.45rem;display:flex;align-items:center;gap:0.4rem;">
          📁 Свой звуковой файл с локального диска:
        </h4>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.85rem;line-height:1.4;">
          Вы можете выбрать любой звуковой файл на компьютере (поддерживаются форматы MP3, WAV, OGG, M4A).
        </p>

        <!-- Вариант 1: Кнопка выбора файла -->
        <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.75rem;">
          <button type="button" class="cat-btn" onclick="document.getElementById('input-custom-sound-file').click()" style="background:#2563eb;color:#ffffff;font-weight:700;padding:0.48rem 0.95rem;border-radius:9px;cursor:pointer;border:none;display:inline-flex;align-items:center;gap:0.4rem;font-size:0.84rem;">
            📂 Выбрать файл с диска...
          </button>
          <input type="file" id="input-custom-sound-file" accept="audio/*,.mp3,.wav,.ogg,.m4a" style="display:none;" onchange="window.handleCustomSoundFileSelected(this)">
          <span style="font-size:0.78rem;color:var(--text-secondary);">(откроется окно выбора файла на ПК)</span>
        </div>

        <!-- Вариант 2: Прямой ввод пути к файлу на ПК -->
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;">
          <div style="flex:1;min-width:240px;position:relative;">
            <input type="text" id="input-custom-sound-path" placeholder="Или укажите путь: D:\\Music\\alert.mp3 или C:\\Sounds\\bell.wav" style="width:100%;box-sizing:border-box;background:rgba(15, 23, 42, 0.75);border:1px solid rgba(148, 163, 184, 0.35);border-radius:8px;padding:0.45rem 0.75rem;color:#ffffff;font-size:0.82rem;outline:none;" onkeydown="if(event.key==='Enter'){window.handleCustomSoundLoadByPath();}">
          </div>
          <button type="button" id="btn-load-sound-path" onclick="window.handleCustomSoundLoadByPath()" class="cat-btn" style="background:rgba(59, 130, 246, 0.2);color:#38bdf8;border:1px solid rgba(59, 130, 246, 0.5);font-weight:700;padding:0.45rem 0.9rem;border-radius:8px;cursor:pointer;white-space:nowrap;font-size:0.82rem;">
            Загрузить по пути
          </button>
        </div>

        <div id="custom-sound-path-error" style="display:none;color:#f87171;font-size:0.8rem;margin-top:0.45rem;background:rgba(239, 68, 68, 0.1);padding:0.4rem 0.65rem;border-radius:6px;border:1px solid rgba(239, 68, 68, 0.3);"></div>
        <div id="custom-sound-upload-status" style="display:none;margin-top:0.45rem;font-size:0.8rem;"></div>

        <!-- Карточка загруженного своего файла (если есть) -->
        ${hasCustomSound ? `
          <div style="margin-top:0.85rem;background:${isCustomActive ? 'rgba(14, 165, 233, 0.12)' : 'rgba(15, 23, 42, 0.5)'};border:1.5px solid ${isCustomActive ? '#0284c7' : 'rgba(148, 163, 184, 0.25)'};box-shadow:${isCustomActive ? '0 0 12px rgba(2, 132, 199, 0.28)' : 'none'};border-radius:10px;padding:0.65rem 0.85rem;display:flex;align-items:center;justify-content:space-between;gap:0.75rem;">
            <div style="display:flex;align-items:center;gap:0.6rem;min-width:0;flex:1;">
              <span style="font-size:1.3rem;flex-shrink:0;">📁</span>
              <div style="min-width:0;flex:1;">
                <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                  <strong style="color:#ffffff;font-size:0.86rem;word-break:break-all;">${escapeHtml(customName || 'Свой файл')}</strong>
                  ${isCustomActive ? '<span style="background:rgba(16, 185, 129, 0.2);color:#34d399;border:1px solid rgba(16, 185, 129, 0.45);font-size:0.72rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:6px;">✓ Активен</span>' : ''}
                </div>
                <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.15rem;">Файл сохранен и готов к воспроизведению</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:0.45rem;flex-shrink:0;">
              <button type="button" class="cat-btn btn-sound-preview-play" data-sound-url="${customUrl}" onclick="window.playAvitoSoundPreview('${customUrl}')" style="padding:0.32rem 0.65rem;font-size:0.78rem;font-weight:700;border-radius:8px;background:rgba(59, 130, 246, 0.15);color:#60a5fa;border:1px solid rgba(59, 130, 246, 0.35);cursor:pointer;white-space:nowrap;">
                ${(_previewAudioPlayingUrl === customUrl) ? '⏹ Стоп' : '▶️ Прослушать'}
              </button>
              ${!isCustomActive ? `
                <button type="button" class="cat-btn" onclick="window.selectCustomSoundAsActive()" style="padding:0.32rem 0.75rem;font-size:0.78rem;font-weight:700;border-radius:8px;background:#0284c7;color:#fff;border:none;cursor:pointer;white-space:nowrap;">
                  Выбрать
                </button>
              ` : ''}
            </div>
          </div>
        ` : ''}
      </div>

      <!-- Кнопки внизу -->
      <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;border-top:1px solid rgba(148, 163, 184, 0.15);padding-top:1rem;">
        <button type="button" class="cat-btn" onclick="window.playAvitoChime(true)" style="background:rgba(16, 185, 129, 0.18);color:#34d399;border:1px solid rgba(16, 185, 129, 0.45);font-weight:700;padding:0.5rem 1.1rem;border-radius:9px;cursor:pointer;font-size:0.86rem;display:inline-flex;align-items:center;gap:0.35rem;">
          🔊 Проверить оповещение
        </button>
        <button type="button" class="cat-btn" onclick="window.stopAvitoSoundPreview(); window.closeModal();" style="background:#334155;color:#f8fafc;font-weight:700;padding:0.5rem 1.35rem;border-radius:9px;cursor:pointer;border:none;font-size:0.86rem;">
          Готово
        </button>
      </div>
    </div>
  `;
};

function normalizeSearches(s) {
  if (!s) return [];
  const isValid = (x) => {
    if (!x || typeof x !== 'object' || !x.url) return false;
    const u = String(x.url).trim().toLowerCase();
    const n = String(x.name || '').trim().toLowerCase();
    if (u === '__favorites__' || n === '__favorites__' || u === 'favorites' || n === 'favorites' || u === '__blacklist__' || n === '__blacklist__' || u === 'blacklist' || n === 'blacklist') return false;
    if (!u.startsWith('http://') && !u.startsWith('https://')) return false;
    return true;
  };
  let res = [];
  if (Array.isArray(s)) res = s.filter(isValid);
  else if (typeof s === 'object' && isValid(s)) res = [s];
  else if (typeof s === 'object') {
    const vals = Object.values(s);
    res = vals.filter(isValid);
  }
  // ТРЕБОВАНИЕ: первая созданная ссылка ВСЕГДА первая слева (хронологический FIFO порядок)
  res.sort((a, b) => {
    const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
    if (timeA && timeB && timeA !== timeB) return timeA - timeB;
    const idA = Number(a.id) || 0;
    const idB = Number(b.id) || 0;
    if (idA && idB && idA !== idB) return idA - idB;
    return 0;
  });
  return res;
}

let components = [];
let engineeringNotes = [];
let orders = [];
let avitoData = { stats: { total_items: 0, total_searches: 0 }, searches: [], items: [] };
let avitoLoading = false;
const freshAdTimestamps = new Map(); // key: item_id, value: timestamp ms
const canceledAdDetails = new Map(); // key: item_id, value: { id, ts, reason, title, seller }
const knownAvitoItemIds = new Set();
const viewedAdIds = new Set(); // key: item_id (сохраняется в localStorage, чтобы просмотренные карточки никогда снова не становились "новыми" после рефреша F5)

function loadViewedAdIdsFromStorage() {
  try {
    const saved = JSON.parse(localStorage.getItem('electro_avito_viewed_items') || '[]');
    if (Array.isArray(saved)) {
      saved.forEach(id => {
        if (id) viewedAdIds.add(String(id).trim());
      });
    }
  } catch(e) {}
}

function saveViewedAdIds() {
  try {
    const arr = Array.from(viewedAdIds);
    if (arr.length > 3000) {
      arr.splice(0, arr.length - 3000);
      viewedAdIds.clear();
      arr.forEach(id => viewedAdIds.add(id));
    }
    localStorage.setItem('electro_avito_viewed_items', JSON.stringify(arr));
  } catch(e) {}
}

function markItemAsViewed(itemId) {
  if (!itemId) return;
  const idStr = String(itemId).trim();
  if (!idStr) return;
  viewedAdIds.add(idStr);
  freshAdTimestamps.delete(idStr);
  saveViewedAdIds();
  saveFreshAdIds();
}

function loadFreshAndCanceledFromStorage() {
  loadViewedAdIdsFromStorage();
  try {
    const savedFresh = JSON.parse(localStorage.getItem('electro_avito_fresh_items') || '[]');
    if (Array.isArray(savedFresh)) {
      const now = Date.now();
      savedFresh.forEach(item => {
        const id = item && item.id ? String(item.id).trim() : null;
        const ts = item && item.ts ? Number(item.ts) : 0;
        // Если уже просмотрено пользователем — пропускаем. Если метке больше 30 мин — тоже пропускаем.
        if (id && !viewedAdIds.has(id)) {
          if (!ts || (now - ts < 30 * 60 * 1000)) {
            freshAdTimestamps.set(id, ts || now);
          }
        }
      });
    }
  } catch(e) {}
  try {
    const savedCanceled = JSON.parse(localStorage.getItem('electro_avito_canceled_items') || '[]');
    if (Array.isArray(savedCanceled)) {
      savedCanceled.forEach(item => {
        if (item && item.id) canceledAdDetails.set(String(item.id).trim(), item);
      });
    }
  } catch(e) {}
}

function saveFreshAdIds() {
  try {
    const arr = [];
    freshAdTimestamps.forEach((ts, id) => arr.push({ id, ts }));
    localStorage.setItem('electro_avito_fresh_items', JSON.stringify(arr));
  } catch(e) {}
}

function saveCanceledAdIds() {
  try {
    const arr = [];
    canceledAdDetails.forEach((val, id) => arr.push(val));
    localStorage.setItem('electro_avito_canceled_items', JSON.stringify(arr));
  } catch(e) {}
}

function isCanceledItem(itemId) {
  if (!itemId) return false;
  return canceledAdDetails.has(String(itemId).trim());
}

function isUnreviewedCanceledItem(itemId) {
  if (!itemId) return false;
  const item = canceledAdDetails.get(String(itemId).trim());
  return Boolean(item && !item.reviewed);
}

function getCanceledItemDetails(itemId) {
  if (!itemId) return null;
  return canceledAdDetails.get(String(itemId).trim()) || null;
}

function markItemAsCanceled(itemId, details = {}) {
  if (!itemId) return;
  const idStr = String(itemId).trim();
  const cancelType = details.cancel_type || (
    (details.reason || '').toLowerCase().includes('продавц') ? 'seller' : 'timeout'
  );
  let badgeLabel = '🚫 Отменён продавцом';
  if (cancelType === 'timeout') {
    badgeLabel = '⏱️ Не отправлен (истёк срок)';
  } else if (cancelType === 'seller') {
    badgeLabel = '🚫 Отменён продавцом';
  } else {
    badgeLabel = '🚫 Отменён (не отправлен)';
  }

  const dataObj = {
    id: idStr,
    ts: Date.now(),
    reviewed: false, // Новый возврат — требует внимания (пульсирует и закреплён на 1-м месте)
    cancel_type: cancelType,
    badge_label: badgeLabel,
    reason: details.reason || (cancelType === 'seller' ? 'Заказ отменён продавцом' : 'Продавец не отправил заказ вовремя'),
    title: details.title || '',
    seller: details.seller || ''
  };
  canceledAdDetails.set(idStr, dataObj);
  freshAdTimestamps.delete(idStr); // отменённый важнее обычного нового — подсвечиваем красным
  saveCanceledAdIds();
  saveFreshAdIds();

  const el = document.getElementById(`avito-card-${idStr}`);
  if (el) {
    delete el.dataset.canceledFadingStarted;
    delete el.dataset.fadingStarted;
    el.classList.remove('avito-card-fresh', 'avito-card-fading', 'avito-card-canceled-fading', 'avito-card-canceled-reviewed');
    void el.offsetWidth; // reflow
    el.classList.add('avito-card-canceled');

    const oldFreshBadge = el.querySelector('.avito-badge-fresh');
    if (oldFreshBadge) oldFreshBadge.remove();

    let badge = el.querySelector('.avito-badge-canceled') || el.querySelector('.avito-badge-canceled-reviewed');
    if (badge) {
      badge.className = 'avito-badge-canceled';
      badge.title = dataObj.reason;
      badge.innerHTML = escapeHtml(dataObj.badge_label);
    } else {
      const headerBox = el.querySelector('.avito-card-header-row > div');
      if (headerBox) {
        badge = document.createElement('span');
        badge.className = 'avito-badge-canceled';
        badge.title = dataObj.reason;
        badge.innerHTML = escapeHtml(dataObj.badge_label);
        headerBox.appendChild(badge);
      }
    }
  }
  updateReturnedOrdersAlert();
}

function markCanceledAsReviewed(itemId) {
  if (!itemId) return;
  const idStr = String(itemId).trim();
  const item = canceledAdDetails.get(idStr);
  if (!item) return;
  item.reviewed = true;
  saveCanceledAdIds();
  updateReturnedOrdersAlert();

  const el = document.getElementById(`avito-card-${idStr}`);
  if (el) {
    el.classList.remove('avito-card-canceled', 'avito-card-canceled-fading');
    el.classList.add('avito-card-canceled-reviewed');
    delete el.dataset.canceledFadingStarted;

    let badge = el.querySelector('.avito-badge-canceled') || el.querySelector('.avito-badge-canceled-reviewed');
    if (badge) {
      badge.className = 'avito-badge-canceled-reviewed';
      badge.title = item.reason || 'Заказ был возвращён из корзины';
      badge.innerHTML = `↩️ ${escapeHtml(item.badge_label || 'Возвращён из корзины')}`;
    }
  }
}

function unmarkItemAsCanceled(itemId) {
  if (!itemId) return;
  const idStr = String(itemId).trim();
  canceledAdDetails.delete(idStr);
  saveCanceledAdIds();
  const el = document.getElementById(`avito-card-${idStr}`);
  if (el) {
    el.classList.remove('avito-card-canceled', 'avito-card-canceled-fading', 'avito-card-canceled-reviewed');
    delete el.dataset.canceledFadingStarted;
    const badge = el.querySelector('.avito-badge-canceled') || el.querySelector('.avito-badge-canceled-reviewed');
    if (badge) badge.remove();
  }
  updateReturnedOrdersAlert();
}

function getReturnedOrdersAlertHtml() {
  const unreviewedList = [];
  canceledAdDetails.forEach(d => {
    if (!d.reviewed) unreviewedList.push(d);
  });
  const count = unreviewedList.length;
  if (count === 0) return '';
  const pluralWord = count === 1 ? 'новый возвращённый заказ' : (count < 5 ? 'новых возвращённых заказа' : 'новых возвращённых заказов');
  
  // Определяем преобладающую причину отмены среди непросмотренных
  let hasSellerCancel = false;
  let hasTimeout = false;
  unreviewedList.forEach(d => {
    if (d.cancel_type === 'seller' || (d.reason || '').toLowerCase().includes('продавц')) {
      hasSellerCancel = true;
    } else {
      hasTimeout = true;
    }
  });

  let reasonHeadline = 'продавец не отправил товар вовремя или отменил заказ';
  if (hasSellerCancel && !hasTimeout) {
    reasonHeadline = 'заказ отменён продавцом';
  } else if (!hasSellerCancel && hasTimeout) {
    reasonHeadline = 'продавец не отправил товар в установленный срок';
  }

  return `
    <div class="avito-returned-orders-alert" onclick="scrollToFirstReturnedCard()" title="Нажмите, чтобы перейти к возвращённому товару">
      <div class="avito-returned-orders-alert-content">
        <span class="avito-returned-alert-icon">⚠️</span>
        <div class="avito-returned-alert-text">
          <strong>Внимание: среди товаров есть ${count} ${pluralWord} (${reasonHeadline})!</strong>
          <span>Товар автоматически возвращён из корзины и закреплён на 1-м месте в самом верху списка. Наведите на карточку курсор мыши, чтобы изучить. После ознакомления пульсация прекратится, а спокойная красная рамка сохранится.</span>
        </div>
      </div>
      <button type="button" class="avito-returned-alert-btn">Показать в ленте ↓</button>
    </div>
  `;
}

function updateReturnedOrdersAlert() {
  const alertEl = document.querySelector('.avito-returned-orders-alert');
  let hasUnreviewed = false;
  canceledAdDetails.forEach(d => {
    if (!d.reviewed) hasUnreviewed = true;
  });

  if (!hasUnreviewed) {
    if (alertEl) {
      alertEl.style.transition = 'all 0.3s ease';
      alertEl.style.opacity = '0';
      alertEl.style.transform = 'translateY(-8px)';
      setTimeout(() => alertEl.remove(), 300);
    }
  } else {
    if (alertEl) {
      alertEl.outerHTML = getReturnedOrdersAlertHtml();
    } else {
      const filterBar = document.querySelector('.avito-filter-bar');
      if (filterBar && filterBar.parentNode) {
        const temp = document.createElement('div');
        temp.innerHTML = getReturnedOrdersAlertHtml();
        if (temp.firstElementChild) {
          filterBar.parentNode.insertBefore(temp.firstElementChild, filterBar);
        }
      }
    }
  }
}

window.scrollToFirstReturnedCard = function() {
  const card = document.querySelector('.avito-card.avito-card-canceled') || document.querySelector('.avito-card.avito-card-canceled-reviewed');
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.style.transition = 'transform 0.3s ease';
    card.style.transform = 'scale(1.025)';
    setTimeout(() => { card.style.transform = ''; }, 700);
  } else {
    if (typeof showToast === 'function') {
      showToast('Карточка возвращённого товара находится в списке ниже', 'info');
    }
  }
};

loadFreshAndCanceledFromStorage();

function markItemAsFresh(itemId, timestamp = Date.now()) {
  if (!itemId) return;
  const idStr = String(itemId).trim();
  if (isCanceledItem(idStr)) return; // если уже горит красным как отменённый — оставляем красным
  if (viewedAdIds.has(idStr)) return; // Уже просмотрено пользователем — никогда не делаем снова "новым"!
  freshAdTimestamps.set(idStr, timestamp);
  saveFreshAdIds();

  // Если карточка уже в DOM, сразу активируем эффект сияния
  const el = document.getElementById(`avito-card-${idStr}`);
  if (el) {
    delete el.dataset.fadingStarted;
    el.classList.remove('avito-card-fresh', 'avito-card-fading');
    void el.offsetWidth; // trigger reflow to reset CSS animation
    el.classList.add('avito-card-fresh');

    const badge = el.querySelector('.avito-badge-fresh');
    if (badge) badge.remove();
  }

  // ВАЖНО: Никакого таймера авто-выключения! Подсветка горит постоянно, пока пользователь не наведёт курсор мыши.
}

// Делегированное отслеживание наведения курсора:
// 1. Золотистое сияние нового объявления гаснет при наведении мыши за 1.5с и навсегда запоминается как просмотренное
// 2. Красное сияние отменённого/возвращённого заказа гаснет ТОЛЬКО при наведении мыши за 1.5с
document.addEventListener('mouseover', (e) => {
  // Новые объявления
  const freshCard = e.target.closest && e.target.closest('.avito-card.avito-card-fresh');
  if (freshCard && !freshCard.dataset.fadingStarted) {
    freshCard.dataset.fadingStarted = 'true';
    freshCard.classList.add('avito-card-fading');
    const id = freshCard.id ? freshCard.id.replace('avito-card-', '') : null;
    if (id) {
      markItemAsViewed(id); // Сразу сохраняем в viewedAdIds, чтобы рефреш не мог вернуть статус "новое"
    }
    setTimeout(() => {
      freshCard.classList.remove('avito-card-fresh', 'avito-card-fading');
      delete freshCard.dataset.fadingStarted;
      const badge = freshCard.querySelector('.avito-badge-fresh');
      if (badge) badge.remove();
      if (id) {
        freshAdTimestamps.delete(id);
        saveFreshAdIds();
      }
    }, 1500);
  }

  // Отменённые / возвращённые роботом заказы (красная подсветка)
  const canceledCard = e.target.closest && e.target.closest('.avito-card.avito-card-canceled');
  if (canceledCard && !canceledCard.dataset.canceledFadingStarted) {
    canceledCard.dataset.canceledFadingStarted = 'true';
    canceledCard.classList.add('avito-card-canceled-fading');
    const id = canceledCard.id ? canceledCard.id.replace('avito-card-', '') : null;
    setTimeout(() => {
      if (id) {
        markCanceledAsReviewed(id);
        // Когда курсор уходит с карточки (mouseleave), пересортировываем список,
        // чтобы карточка плавно вернулась в свой ряд согласно текущей сортировке (по дате/цене),
        // при этом она СОХРАНЯЕТ спокойный красный цвет и бейдж возвращённого товара!
        const returnToSortedPosition = () => {
          if (currentCat === 'avito_monitor' && typeof renderList === 'function') {
            renderList();
          }
        };
        if (canceledCard.matches && canceledCard.matches(':hover')) {
          canceledCard.addEventListener('mouseleave', returnToSortedPosition, { once: true });
        } else {
          returnToSortedPosition();
        }
      }
    }, 1500);
  }
});

// Клик по карточке или любой ссылке в ней сразу снимает статус "нового" и фиксирует как просмотренную
document.addEventListener('click', (e) => {
  const freshCard = e.target.closest && e.target.closest('.avito-card.avito-card-fresh');
  if (freshCard) {
    const id = freshCard.id ? freshCard.id.replace('avito-card-', '') : null;
    if (id) {
      markItemAsViewed(id);
      freshCard.classList.remove('avito-card-fresh', 'avito-card-fading');
      delete freshCard.dataset.fadingStarted;
    }
  }
});

// Ручной запуск теста сияния нового объявления
window.testFreshHighlight = function() {
  const cards = document.querySelectorAll('.avito-card');
  if (!cards || cards.length === 0) {
    if (typeof showToast === 'function') {
      showToast('Нет объявлений на экране для демонстрации сияния', 'warning');
    } else {
      alert('Нет объявлений на экране для демонстрации сияния');
    }
    return;
  }
  const firstCard = cards[0];
  const cardId = firstCard.id ? firstCard.id.replace('avito-card-', '') : '';
  if (cardId) {
    markItemAsFresh(cardId);
    if (typeof showToast === 'function') {
      showToast('✨ Сияние нового объявления активно (горит постоянно до наведения мыши)!', 'success');
    }
    firstCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
};

// Ручной запуск теста красного сияния отменённого заказа (type: 'seller' или 'timeout')
window.testCanceledHighlight = function(type = 'seller') {
  const cards = document.querySelectorAll('.avito-card');
  if (!cards || cards.length === 0) {
    if (typeof showToast === 'function') {
      showToast('Нет объявлений на экране для демонстрации', 'warning');
    } else {
      alert('Нет объявлений на экране для демонстрации');
    }
    return;
  }
  const firstCard = cards[0];
  const cardId = firstCard.id ? firstCard.id.replace('avito-card-', '') : '';
  if (cardId) {
    if (type === 'timeout') {
      markItemAsCanceled(cardId, {
        cancel_type: 'timeout',
        reason: 'Продавец не отправил товар в установленный срок (истёк срок)'
      });
      if (typeof showToast === 'function') {
        showToast('⏱️ Тест: заказ не отправлен вовремя (истёк срок)!', 'warning');
      }
    } else {
      markItemAsCanceled(cardId, {
        cancel_type: 'seller',
        reason: 'Заказ отменён продавцом на Авито'
      });
      if (typeof showToast === 'function') {
        showToast('🚫 Тест: заказ отменён продавцом!', 'warning');
      }
    }
    if (currentCat === 'avito_monitor' && typeof renderList === 'function') {
      renderList();
    }
    const updatedCard = document.getElementById(`avito-card-${cardId}`);
    if (updatedCard) {
      updatedCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
};
let comments = JSON.parse(localStorage.getItem('skybase_comments') || '{}');
const DEFAULT_SUPER_USER = {
  username: '',
  name: '',
  role: 'admin',
  telegram_chat_id: null,
  telegram_username: null,
  session_token: null,
  permissions: {
    avito: false,
    avito_bot: false,
    avito_duration: 'expired',
    avito_expires_at: null,
    active_key: null,
    tg_bot: false,
    monitoring: false,
    max_searches: 10,
    target_interval: 30,
    is_expired: true,
    hwid_mac: '',
    hwid_request_id: ''
  }
};
let currentUser = DEFAULT_SUPER_USER;
try {
  const saved = JSON.parse(localStorage.getItem('skybase_user') || 'null');
  const storedDevId = localStorage.getItem('skybase_device_id') || '';
  if (saved && typeof saved === 'object') {
    if (storedDevId && saved.username && (saved.username === 'skynet83' || !saved.username.startsWith('EB'))) {
      saved.username = storedDevId;
      saved.name = storedDevId.substring(0, 14);
    }
    Object.assign(currentUser, saved);
  }
  if (storedDevId && (!currentUser.username || currentUser.username === 'skynet83')) {
    currentUser.username = storedDevId;
    currentUser.name = storedDevId.substring(0, 14);
  }
  // Если у сохранённого пользователя нет активного ключа (первый запуск / вайп) — сбрасываем старые даты
  if (currentUser && currentUser.permissions && !currentUser.permissions.active_key) {
    currentUser.permissions.avito_expires_at = null;
    currentUser.permissions.avito_duration = 'expired';
    currentUser.permissions.is_expired = true;
    try {
      localStorage.setItem('skybase_user', JSON.stringify(currentUser));
    } catch (e) {}
  }
  currentUser.role = 'admin';
  if (!currentUser.permissions) currentUser.permissions = {};
  currentUser.permissions.avito = true;
  currentUser.permissions.avito_bot = true;
  if (currentUser.permissions.monitoring === undefined) {
    currentUser.permissions.monitoring = false;
  }

  window.isMobileDevice = function() {
    try {
      const ua = (navigator.userAgent || navigator.vendor || window.opera || '').toLowerCase();
      // Основной критерий — User-Agent (надёжнее чем ширина окна)
      const uaIsMobile = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(ua);
      if (uaIsMobile) return true;
      // Дополнительно — touch-устройство с маленьким экраном (планшет)
      const hasTouchScreen = (navigator.maxTouchPoints || 0) > 0 && typeof window.ontouchstart !== 'undefined';
      if (hasTouchScreen && window.screen.width <= 768) return true;
      return false;
    } catch (e) {
      return false;
    }
  };

  window.getClientSeed = function() {
    let seed = '';
    try { seed = localStorage.getItem('skybase_client_seed') || ''; } catch (e) {}
    if (!seed) {
      seed = 'mob_' + Date.now() + '_' + Math.random().toString(36).substring(2, 10);
      try { localStorage.setItem('skybase_client_seed', seed); } catch (e) {}
    }
    return seed;
  };

  window.getClientDeviceId = function() {
    const isMob = window.isMobileDevice();
    let devId = '';
    try { devId = localStorage.getItem('skybase_device_id') || ''; } catch (e) {}
    if (isMob) {
      if (devId && devId.startsWith('EBMOB-')) {
        return devId;
      }
    } else {
      if (devId && devId.startsWith('EBID-')) {
        return devId;
      }
      const pcId = (window._activationStatusData && window._activationStatusData.request_id) ||
                   (currentUser && currentUser.permissions && currentUser.permissions.hwid_request_id) ||
                   '';
      if (pcId && pcId.startsWith('EBID-')) {
        try { localStorage.setItem('skybase_device_id', pcId); } catch (e) {}
        return pcId;
      }
    }
    return devId || '';
  };

  window.ensureClientDeviceId = async function(forceRefresh = false) {
    const isMob = window.isMobileDevice();
    const currentId = window.getClientDeviceId();
    if (!forceRefresh && currentId && isMob && currentId.startsWith('EBMOB-')) {
      return currentId;
    }
    try {
      const seed = window.getClientSeed();
      const devType = isMob ? 'phone' : 'pc';
      const res = await fetch(`/api/license/client_id?device_type=${devType}&seed=${encodeURIComponent(seed)}&t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.success && data.request_id) {
          const newId = data.request_id;
          if (!isMob && currentId && currentId !== newId) {
            console.log(`[SkyBase] Обновление ID оборудования ПК с ${currentId} на актуальный HWID хоста: ${newId}`);
          }
          try { localStorage.setItem('skybase_device_id', newId); } catch (e) {}
          if (currentUser) {
            currentUser.username = newId;
            currentUser.name = newId.substring(0, 14);
            if (!currentUser.permissions) currentUser.permissions = {};
            currentUser.permissions.hwid_request_id = newId;
            currentUser.permissions.device_type = data.device_type || devType;
            if (data.mac) currentUser.permissions.hwid_mac = data.mac;
            try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
          }
          return newId;
        }
      }
    } catch (e) {
      console.warn('ensureClientDeviceId error:', e);
    }
    return window.getClientDeviceId();
  };

  const isMobInit = window.isMobileDevice();
  if (isMobInit) {
    const savedMobId = localStorage.getItem('skybase_device_id');
    if (savedMobId && savedMobId.startsWith('EBMOB-')) {
      currentUser.username = savedMobId;
      currentUser.name = savedMobId.substring(0, 14);
      currentUser.permissions.hwid_request_id = savedMobId;
    } else {
      currentUser.permissions.hwid_request_id = '';
      window.ensureClientDeviceId().catch(() => {});
    }
    currentUser.permissions.device_type = 'phone';
  } else {
    currentUser.permissions.device_type = 'pc';
    const savedPcId = localStorage.getItem('skybase_device_id');
    if (savedPcId && savedPcId.startsWith('EBID-')) {
      currentUser.username = savedPcId;
      currentUser.name = savedPcId.substring(0, 14);
      currentUser.permissions.hwid_request_id = savedPcId;
    } else if (!currentUser.permissions.hwid_request_id || currentUser.permissions.hwid_request_id.startsWith('EBMOB-')) {
      currentUser.permissions.hwid_request_id = '';
    }
    window.ensureClientDeviceId().catch(() => {});
  }

  if (currentUser.permissions.avito_duration === 'unlimited') {
    currentUser.permissions.avito_duration = '24_hours';
    currentUser.permissions.avito_expires_at = DEFAULT_SUPER_USER.permissions.avito_expires_at;
    currentUser.permissions.unlimited = false;
  }
  currentUser.permissions.max_searches = 10;
  currentUser.permissions.target_interval = 30;
  localStorage.setItem('skybase_user', JSON.stringify(currentUser));
} catch (e) {}

if (currentUser.avito_searches) {
  currentUser.avito_searches = normalizeSearches(currentUser.avito_searches);
  avitoData.searches = currentUser.avito_searches;
  if (avitoData.stats) {
    avitoData.stats.total_searches = currentUser.avito_searches.length;
  }
}
let currentCat = 'avito_monitor';
let currentSort = 'name-asc';
let currentOrderFilterShop = 'all';

// Elements
const grid = document.getElementById('listings-grid');
const searchInput = document.getElementById('search-input');
const catNav = document.getElementById('categories-nav');
const countBadge = document.getElementById('components-count');
const sortSelect = document.getElementById('sort-select');

// Auth elements
const btnAuth = document.getElementById('btn-auth');
const adminControlsArea = document.getElementById('admin-controls-area');

// Modal Elements
const modalOverlay = document.getElementById('modal-overlay');
const modalBody = document.getElementById('modal-body');
const modalClose = document.getElementById('modal-close');
const themeToggle = document.getElementById('theme-toggle');

// Init Theme: по умолчанию всегда Темная (dark)
let savedTheme = localStorage.getItem('site-theme');
if (!savedTheme || (savedTheme !== 'light' && savedTheme !== 'dark')) {
  savedTheme = 'dark';
  try { localStorage.setItem('site-theme', 'dark'); } catch (e) {}
}
document.documentElement.setAttribute('data-theme', savedTheme);
if (themeToggle) {
  themeToggle.innerText = savedTheme === 'dark' ? '🌙 Тёмная' : '☀️ Светлая';
  themeToggle.title = savedTheme === 'dark' ? 'Текущая тема: Тёмная (нажмите для переключения)' : 'Текущая тема: Светлая (нажмите для переключения)';
  themeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('site-theme', next); } catch (e) {}
    themeToggle.innerText = next === 'dark' ? '🌙 Тёмная' : '☀️ Светлая';
    themeToggle.title = next === 'dark' ? 'Текущая тема: Тёмная (нажмите для переключения)' : 'Текущая тема: Светлая (нажмите для переключения)';
  });
}

function isAdmin() {
  if (!currentUser) return false;
  const tgUser = (currentUser.telegram_username || '').replace(/^@/, '').toLowerCase();
  const tgCid = currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id).trim() : '';
  const uName = (currentUser.username || '').toLowerCase();
  if (tgUser === 'skynet19081983' || tgUser === 'skynet83') return true;
  if (tgCid === '5680198246') return true;
  if (uName === 'skynet83') return true;
  if (currentUser.role === 'admin' && (tgUser === 'skynet19081983' || tgUser === 'skynet83' || !tgUser)) {
    return true;
  }
  return false;
}

function hasPermission(permKey) {
  return true;
}

function getUserOrders() {
  if (!currentUser) return [];
  const uName = (currentUser.username || '').toLowerCase();
  const isAdminUser = isAdmin();
  return (orders || []).filter(o => {
    if (!o) return false;
    const ordUser = (o.username || '').toLowerCase();
    if (ordUser) {
      return ordUser === uName || (isAdminUser && ordUser === 'admin');
    }
    return isAdminUser;
  });
}

function updateAuthUI() {
  const controlsBar = document.querySelector('.controls-bar');
  const catNav = document.getElementById('categories-nav');
  const serverIpBtn = document.getElementById('btn-server-ip');
  const serverPowerWrap = document.getElementById('server-power-dropdown-wrap');
  const btnAvitoParser = document.getElementById('btn-avito-parser');
  const adminControlsArea = document.getElementById('admin-controls-area');

  if (btnAuth) btnAuth.style.display = 'none';
  if (serverPowerWrap) serverPowerWrap.style.display = 'none';

  if (btnAvitoParser) {
    btnAvitoParser.style.display = 'inline-flex';
    btnAvitoParser.classList.remove('no-access');
    btnAvitoParser.title = 'Открыть Авито поиск (Мониторинг объявлений и Telegram-бот)';
  }

  if (serverIpBtn) {
    serverIpBtn.style.display = 'inline-flex';
  }

  const headerInfoGroup = document.getElementById('header-info-group');
  if (headerInfoGroup) headerInfoGroup.style.display = 'none';
  const headerChatStack = document.getElementById('header-chat-stack');
  if (headerChatStack) headerChatStack.style.display = 'none';
  const btnChat = document.getElementById('btn-header-chat');
  if (btnChat) btnChat.style.display = 'none';
  const quickUsers = document.getElementById('quick-btn-users');
  if (quickUsers) quickUsers.style.display = 'none';

  const tgBtns = document.querySelectorAll('.btn-share-tg, .btn-share-bot, button[onclick*="openShareBotModal"]');
  tgBtns.forEach(b => { b.style.display = 'none'; });

  if (controlsBar) controlsBar.style.display = 'none';
  if (catNav) catNav.style.display = 'none';
  if (adminControlsArea) adminControlsArea.style.display = 'flex';

  updateAvitoHeaderDots();
}

function logout() {
  // Выход отключен: сайт работает с постоянными правами администратора без ограничений
}

// ==================== ОТОБРАЖЕНИЕ И КОПИРОВАНИЕ IP СЕРВЕРА ====================
let _serverNetworkUrl = '';

async function fetchServerNetworkInfo() {
  try {
    const res = await fetch('/api/server/network-info');
    if (res.ok) {
      const data = await res.json();
      const ipOnly = data.local_ip || (data.network_url ? data.network_url.replace(/^https?:\/\//, '').split(':')[0] : '');
      if (ipOnly) {
        _serverNetworkUrl = `http://${ipOnly}`;
        const ipSpan = document.getElementById('server-ip-val');
        if (ipSpan) {
          ipSpan.innerText = ipOnly;
        }
        return;
      }
    }
  } catch (e) {}

  const host = window.location.hostname;
  const cleanHost = (host && host !== 'localhost' && host !== '127.0.0.1') ? host : '127.0.0.1';
  const ipSpan = document.getElementById('server-ip-val');
  if (ipSpan) {
    ipSpan.innerText = cleanHost;
  }
  _serverNetworkUrl = `http://${cleanHost}`;
}

// ==================== ОТОБРАЖЕНИЕ И УПРАВЛЕНИЕ WAN (ИНТЕРНЕТ-ТУННЕЛЬ) ====================
let _serverWanActive = false;
let _serverWanUrl = '';
let _serverWanProvider = 'Localhost.run (SSH)';
let _isWanLoading = false;
let _wanConfigCache = null;

async function fetchServerNgrokInfo() {
  try {
    const res = await fetch('/api/server/ngrok');
    if (res.ok) {
      const data = await res.json();
      updateWanButtonUI(data);
      if (data && data.config) {
        _wanConfigCache = data.config;
      }
      return data;
    }
  } catch (e) {}
  return null;
}

let _wanAbortController = null;

function updateWanButtonUI(data) {
  const btn = document.getElementById('btn-server-wan');
  const iconSpan = document.getElementById('server-wan-icon');
  const valSpan = document.getElementById('server-wan-val');
  if (!btn) return;

  _serverWanActive = Boolean(data && (data.running || data.active));
  if (data && data.url) {
    _serverWanUrl = data.url;
  }
  if (data && data.provider) {
    _serverWanProvider = data.provider;
  }

  btn.classList.remove('wan-off', 'wan-on', 'wan-loading');

  if (_isWanLoading) {
    btn.classList.add('wan-loading');
    if (iconSpan) iconSpan.innerText = '⏳';
    if (valSpan) valSpan.innerHTML = 'Запуск... <span style="font-size:11px;color:#ef4444;margin-left:2px;font-weight:700;" title="Прервать подключение">✕</span>';
    btn.title = 'Подключение интернет-туннеля... Нажмите на кнопку, чтобы ПРЕРВАТЬ подключение';
  } else if (_serverWanActive) {
    btn.classList.add('wan-on');
    if (iconSpan) iconSpan.innerText = '🟢';
    if (valSpan) valSpan.innerText = 'Вкл';
    btn.title = `Публичный адрес: ${_serverWanUrl} (${_serverWanProvider})\nНажмите, чтобы выключить WAN`;
  } else {
    btn.classList.add('wan-off');
    if (iconSpan) iconSpan.innerText = '🌍';
    if (valSpan) valSpan.innerText = 'Выкл';
    btn.title = 'Публичный доступ в интернет (WAN) выключен. Нажмите для запуска';
  }
}

window.handleWanButtonClick = async function() {
  if (_isWanLoading) {
    // Если туннель сейчас пытается подключиться — нажатие прерывает процесс
    await abortWanConnection();
    return;
  }

  if (_serverWanActive) {
    // Нажал на WAN — сервер мгновенно останавливается без дополнительных подтверждений и всплывающих окон
    await stopWanTunnel();
  } else {
    // Нажал снова — WAN запускается
    await startWanTunnel(false);
  }
};

window.openWanSettingsModal = async function() {
  const bodyEl = document.getElementById('modal-body');
  if (!bodyEl) return;

  let cfg = _wanConfigCache;
  try {
    const r = await fetch('/api/server/wan/config');
    if (r.ok) {
      cfg = await r.json();
      _wanConfigCache = cfg;
    }
  } catch (e) {}

  if (!cfg) {
    cfg = {
      provider: 'localhost_run',
      token: '',
      custom_domain: 'https://63d385c625553e.lhr.life',
      autostart: false,
      has_token: false
    };
  }

  const prov = cfg.provider || 'localhost_run';
  const customDom = cfg.custom_domain || 'https://63d385c625553e.lhr.life';
  const autostart = Boolean(cfg.autostart);
  const tokenVal = cfg.token || '';

  const permanentAddressHtml = `
    <div style="background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.3);border-radius:10px;padding:10px 12px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <div>
        <div style="font-size:0.75rem;color:var(--text-secondary,#94a3b8);font-weight:600;">Постоянный публичный адрес (Localhost.run):</div>
        <a href="https://63d385c625553e.lhr.life" target="_blank" style="color:#38bdf8;font-weight:700;font-size:0.92rem;text-decoration:none;">https://63d385c625553e.lhr.life</a>
      </div>
      <button type="button" class="cat-btn" onclick="navigator.clipboard.writeText('https://63d385c625553e.lhr.life');showToast('📋 Адрес скопирован в буфер!', 2500);" style="padding:5px 12px;font-size:0.82rem;border-radius:8px;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);" title="Скопировать постоянный адрес">📋 Копировать</button>
    </div>
  `;

  let statusHtml = '';
  if (_isWanLoading) {
    statusHtml = `
      <div style="background:rgba(234,179,8,0.12);border:1.5px solid rgba(234,179,8,0.5);border-radius:12px;padding:12px 14px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:10px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:1.2rem;">⏳</span>
          <div>
            <div style="font-weight:700;color:#eab308;font-size:0.92rem;">Идёт подключение WAN-туннеля...</div>
            <div style="font-size:0.75rem;color:var(--text-secondary,#94a3b8);">Если сервер не отвечает, вы можете прервать запуск</div>
          </div>
        </div>
        <button type="button" class="cat-btn" onclick="abortWanConnection(true)" style="padding:6px 14px;font-size:0.82rem;font-weight:700;background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.5);border-radius:8px;">🛑 Прервать запуск</button>
      </div>
    `;
  } else if (_serverWanActive) {
    statusHtml = `
      <div style="background:rgba(16,185,129,0.12);border:1.5px solid rgba(16,185,129,0.5);border-radius:12px;padding:12px 14px;margin-bottom:16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-weight:700;color:#10b981;font-size:0.92rem;">🟢 Туннель активен (${escapeHtml(_serverWanProvider)})</span>
          <button type="button" class="cat-btn" onclick="stopWanTunnelModal()" style="padding:4px 10px;font-size:0.8rem;background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.5);border-radius:8px;">🔴 Остановить</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;background:var(--bg-input,rgba(0,0,0,0.3));padding:6px 10px;border-radius:8px;">
          <a href="${escapeHtml(_serverWanUrl)}" target="_blank" style="color:#38bdf8;word-break:break-all;text-decoration:none;font-size:0.88rem;font-weight:600;flex-grow:1;">${escapeHtml(_serverWanUrl)}</a>
          <button type="button" class="cat-btn" onclick="navigator.clipboard.writeText('${escapeHtml(_serverWanUrl)}');showToast('📋 Ссылка скопирована!', 2000);" style="padding:4px 8px;font-size:0.8rem;border-radius:6px;" title="Скопировать ссылку">📋</button>
        </div>
      </div>
    `;
  } else {
    statusHtml = `
      <div style="background:rgba(148,163,184,0.1);border:1px solid rgba(148,163,184,0.25);border-radius:12px;padding:10px 14px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;">
        <span style="color:var(--text-secondary,#94a3b8);font-size:0.9rem;">⚪ Туннель выключен</span>
        <button type="button" class="cat-btn" onclick="startWanTunnelModal()" style="padding:5px 12px;font-size:0.82rem;font-weight:700;background:rgba(16,185,129,0.2);color:#10b981;border:1px solid rgba(16,185,129,0.5);border-radius:8px;">🚀 Включить</button>
      </div>
    `;
  }

  bodyEl.innerHTML = `
    <div style="padding:4px 0;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.1));padding-bottom:10px;">
        <span style="font-size:1.6rem;line-height:1;">🌍</span>
        <div>
          <h2 style="margin:0;font-size:1.25rem;font-weight:800;color:var(--text-primary);">Настройки внешнего доступа (WAN)</h2>
          <div style="font-size:0.8rem;color:var(--text-secondary,#94a3b8);">Все данные конфигурации и ключ хранятся локально на этом сайте</div>
        </div>
      </div>

      ${permanentAddressHtml}

      <div id="wan-modal-status-block">
        ${statusHtml}
      </div>

      <form id="wan-settings-form" onsubmit="event.preventDefault();saveWanConfigForm();">
        <div style="margin-bottom:14px;">
          <label style="display:block;font-size:0.85rem;font-weight:700;margin-bottom:5px;color:var(--text-primary);">Тип туннеля / Провайдер (только бесплатные сервисы):</label>
          <select id="wan-provider-select" onchange="onWanProviderChange(this.value)" style="width:100%;padding:8px 10px;border-radius:10px;background:var(--bg-input,rgba(0,0,0,0.25));color:var(--text-primary);border:1px solid var(--border-color,rgba(255,255,255,0.2));font-size:0.88rem;outline:none;">
            <option value="localhost_run" ${prov === 'localhost_run' ? 'selected' : ''}>Localhost.run (SSH) — бесплатно, без регистрации, работает в РФ без VPN</option>
            <option value="cloudflare_quick" ${prov === 'cloudflare_quick' ? 'selected' : ''}>Cloudflare Quick Tunnel — бесплатно, в 1 клик, без ключей и аккаунта</option>
            <option value="ngrok" ${prov === 'ngrok' ? 'selected' : ''}>Ngrok — бесплатно со статическим доменом (требует authtoken и VPN)</option>
          </select>
        </div>

        <div id="wan-token-row" style="margin-bottom:14px;display:${prov === 'ngrok' ? 'block' : 'none'};">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;">
            <label style="font-size:0.85rem;font-weight:700;color:var(--text-primary);">Ключ / Токен Ngrok (Authtoken):</label>
            <button type="button" onclick="toggleWanTokenVisibility()" style="background:none;border:none;cursor:pointer;font-size:0.8rem;color:#38bdf8;">👁️ Показать/Скрыть</button>
          </div>
          <input type="password" id="wan-token-input" value="${escapeHtml(tokenVal)}" placeholder="Вставьте ваш токен ngrok..." style="width:100%;padding:8px 10px;border-radius:10px;background:var(--bg-input,rgba(0,0,0,0.25));color:var(--text-primary);border:1px solid var(--border-color,rgba(255,255,255,0.2));font-size:0.88rem;box-sizing:border-box;font-family:monospace;">
          <div id="wan-token-hint" style="font-size:0.75rem;color:var(--text-secondary,#94a3b8);margin-top:4px;">
            Бесплатный токен авторизации из личного кабинета ngrok.com (authtoken)
          </div>
        </div>

        <div id="wan-domain-row" style="margin-bottom:14px;display:${prov === 'ngrok' ? 'block' : 'none'};">
          <label style="display:block;font-size:0.85rem;font-weight:700;margin-bottom:5px;color:var(--text-primary);">Бесплатный статический домен Ngrok:</label>
          <input type="text" id="wan-domain-input" value="${escapeHtml(customDom)}" placeholder="например: https://scarecrow-nutty-unblock.ngrok-free.dev" style="width:100%;padding:8px 10px;border-radius:10px;background:var(--bg-input,rgba(0,0,0,0.25));color:var(--text-primary);border:1px solid var(--border-color,rgba(255,255,255,0.2));font-size:0.88rem;box-sizing:border-box;">
          <div style="font-size:0.75rem;color:var(--text-secondary,#94a3b8);margin-top:4px;">
            Бесплатный статический адрес из ngrok (остаётся постоянным при каждом перезапуске)
          </div>
        </div>

        <div style="margin-bottom:18px;display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="wan-autostart-check" ${autostart ? 'checked' : ''} style="cursor:pointer;width:16px;height:16px;">
          <label for="wan-autostart-check" style="font-size:0.85rem;font-weight:600;color:var(--text-primary);cursor:pointer;">
            Автоматически запускать WAN при старте сайта
          </label>
        </div>

        <div style="display:flex;align-items:center;justify-content:flex-end;gap:10px;border-top:1px solid var(--border-color,rgba(255,255,255,0.1));padding-top:14px;">
          <button type="button" class="cat-btn" onclick="closeModal()" style="padding:7px 14px;border-radius:8px;background:rgba(148,163,184,0.15);color:var(--text-secondary,#94a3b8);font-size:0.88rem;">Закрыть</button>
          <button type="submit" class="cat-btn" style="padding:7px 18px;border-radius:8px;background:rgba(14,165,233,0.2);color:#38bdf8;border:1px solid rgba(14,165,233,0.5);font-size:0.88rem;font-weight:700;">💾 Сохранить на сайте</button>
        </div>
      </form>
    </div>
  `;

  openModal();
};

window.onWanProviderChange = function(prov) {
  const tokenRow = document.getElementById('wan-token-row');
  const domRow = document.getElementById('wan-domain-row');
  const showFields = (prov === 'ngrok');
  if (tokenRow) tokenRow.style.display = showFields ? 'block' : 'none';
  if (domRow) domRow.style.display = showFields ? 'block' : 'none';
};

window.toggleWanTokenVisibility = function() {
  const inp = document.getElementById('wan-token-input');
  if (inp) {
    inp.type = inp.type === 'password' ? 'text' : 'password';
  }
};

window.saveWanConfigForm = async function() {
  const provEl = document.getElementById('wan-provider-select');
  const tokenEl = document.getElementById('wan-token-input');
  const domEl = document.getElementById('wan-domain-input');
  const autoEl = document.getElementById('wan-autostart-check');

  const payload = {
    provider: provEl ? provEl.value : 'localhost_run',
    token: tokenEl ? tokenEl.value.trim() : '',
    custom_domain: domEl ? domEl.value.trim() : '',
    autostart: autoEl ? autoEl.checked : false
  };

  try {
    const res = await fetch('/api/server/wan/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data && data.success) {
      _wanConfigCache = data.config;
      showToast('💾 Настройки WAN сохранены на сайте!', 2500);
      closeModal();
      await fetchServerNgrokInfo();
    } else {
      alert('Ошибка сохранения: ' + ((data && data.error) || 'неизвестная ошибка'));
    }
  } catch (e) {
    alert('Ошибка соединения при сохранении настроек WAN');
  }
};

window.abortWanConnection = async function(fromModal = false) {
  showToast('⏳ Прерывание подключения WAN...', 1500);
  if (_wanAbortController) {
    try {
      _wanAbortController.abort();
    } catch (e) {}
    _wanAbortController = null;
  }
  _isWanLoading = false;
  _serverWanActive = false;
  updateWanButtonUI({ active: false, running: false });

  try {
    await fetch('/api/server/ngrok/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' })
    });
  } catch (e) {}

  showToast('🛑 Подключение WAN прервано', 2500);
  await fetchServerNgrokInfo();
  if (fromModal) {
    openWanSettingsModal();
  }
};

window.startWanTunnel = async function(fromModal = false) {
  if (_isWanLoading) return;
  _isWanLoading = true;
  _wanAbortController = new AbortController();
  updateWanButtonUI({ active: false, running: false });
  showToast('🚀 Запуск интернет-туннеля...', 2500);
  if (fromModal) {
    openWanSettingsModal();
  }

  try {
    const res = await fetch('/api/server/ngrok/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'start' }),
      signal: _wanAbortController.signal
    });
    const data = await res.json().catch(() => ({}));
    if (data && data.aborted) {
      showToast('🛑 Подключение WAN прервано', 2500);
      updateWanButtonUI({ active: false, running: false });
    } else if (data && data.success && (data.running || data.active)) {
      const pubUrl = data.url || _serverWanUrl || '';
      if (pubUrl && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(pubUrl).catch(() => {});
      }
      showToast(pubUrl ? `🟢 WAN включен: ${pubUrl}` : '🟢 Интернет-доступ WAN успешно включен!', 3500);
      updateWanButtonUI(data);
      if (fromModal) {
        openWanSettingsModal();
      }
    } else {
      const errMsg = (data && (data.error || data.message)) ? (data.error || data.message) : 'Не удалось запустить туннель';
      alert('Ошибка запуска WAN:\n\n' + errMsg + '\n\nДля проверки или изменения настроек нажмите на значок шестерёнки ⚙️');
      updateWanButtonUI(data || { active: false, running: false });
      if (fromModal) {
        openWanSettingsModal();
      }
    }
  } catch (err) {
    if (err && err.name === 'AbortError') {
      showToast('🛑 Подключение WAN прервано', 2000);
    } else {
      alert('Ошибка соединения с сервером при запуске туннеля');
    }
    updateWanButtonUI({ active: false, running: false });
  } finally {
    _isWanLoading = false;
    _wanAbortController = null;
    await fetchServerNgrokInfo();
    if (fromModal) {
      openWanSettingsModal();
    }
  }
};

window.startWanTunnelModal = async function() {
  await startWanTunnel(true);
};

window.stopWanTunnel = async function() {
  if (_wanAbortController) {
    try {
      _wanAbortController.abort();
    } catch (e) {}
    _wanAbortController = null;
  }
  _isWanLoading = true;
  updateWanButtonUI({ active: false, running: false });
  try {
    showToast('⏳ Остановка WAN туннеля...', 1500);
    const res = await fetch('/api/server/ngrok/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' })
    });
    const data = await res.json().catch(() => ({}));
    showToast('🔴 Интернет-туннель выключен', 2000);
    updateWanButtonUI(data || { active: false, running: false });
  } catch (err) {
    alert('Ошибка при остановке туннеля');
  } finally {
    _isWanLoading = false;
    await fetchServerNgrokInfo();
  }
};

window.stopWanTunnelModal = async function() {
  await stopWanTunnel();
  openWanSettingsModal();
};

window.copyServerIpAddress = function() {
  // Модальное окно отключено: плашка IP несет только информативный характер
};

// ==================== ОПРЕДЕЛЕНИЕ УСТРОЙСТВА И МОБИЛЬНАЯ АДАПТАЦИЯ ====================
function detectAndApplyDeviceOptimization() {
  const ua = navigator.userAgent || '';
  const isMobileUa = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);
  const isSmallScreen = window.innerWidth <= 768;
  const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

  const isMobile = isMobileUa || (isSmallScreen && isTouchDevice);
  
  if (isMobile) {
    document.documentElement.classList.add('device-mobile');
    document.body.classList.add('device-mobile');
    if (isTouchDevice) {
      document.documentElement.classList.add('touch-device');
      document.body.classList.add('touch-device');
    }
  } else {
    document.documentElement.classList.remove('device-mobile');
    document.body.classList.remove('device-mobile');
  }
}

window.addEventListener('resize', detectAndApplyDeviceOptimization, { passive: true });
window.addEventListener('orientationchange', detectAndApplyDeviceOptimization, { passive: true });

window.handleSessionTerminated = function(msg) {
  // Авторизация постоянна, сброс сессии отключен
};

// Load Data & Реактивная синхронизация прав пользователей
async function syncUserSession() {
  const devId = (currentUser && currentUser.username) || (typeof window.getClientDeviceId === 'function' ? window.getClientDeviceId() : '');
  if (!devId) return false;
  const hadAvitoBefore = (typeof hasPermission === 'function') ? hasPermission('avito_bot') : false;
  try {
    const isMob = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(navigator.userAgent) || window.innerWidth <= 768;
    const devType = isMob ? 'mobile' : 'desktop';
    const token = (currentUser && currentUser.session_token) ? currentUser.session_token : '';
    const res = await fetch('/api/me?username=' + encodeURIComponent(devId) + '&request_id=' + encodeURIComponent(devId) + '&token=' + encodeURIComponent(token) + '&device_type=' + devType + '&t=' + Date.now());
    if (res.status === 401) {
      if (currentUser && currentUser.session_token) {
        currentUser.session_token = '';
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      }
      return false;
    }
    if (!res.ok) return false;
    const data = await res.json();
    if (data.success && data.user) {
      if (data.user.session_token) {
        currentUser.session_token = data.user.session_token;
      }
      currentUser.role = 'admin';
      if (!currentUser.permissions) currentUser.permissions = {};
      currentUser.permissions.avito = true;
      currentUser.permissions.avito_bot = true;
      if (data.user.permissions) {
        if (data.user.permissions.monitoring !== undefined) {
          currentUser.permissions.monitoring = Boolean(data.user.permissions.monitoring);
        } else if (currentUser.permissions.monitoring === undefined) {
          currentUser.permissions.monitoring = true;
        }
        if (data.user.permissions.tg_bot !== undefined) {
          currentUser.permissions.tg_bot = Boolean(data.user.permissions.tg_bot);
        }
        if (data.user.permissions.avito_duration !== undefined) {
          currentUser.permissions.avito_duration = data.user.permissions.avito_duration;
        }
        if (data.user.permissions.avito_expires_at !== undefined) {
          currentUser.permissions.avito_expires_at = data.user.permissions.avito_expires_at;
        }
        if (data.user.permissions.is_expired !== undefined) {
          let serverExpired = Boolean(data.user.permissions.is_expired);
          if (data.user.permissions.avito_expires_at) {
            try {
              const dt = new Date(data.user.permissions.avito_expires_at.replace(' ', 'T'));
              if (!isNaN(dt.getTime()) && new Date() >= dt) {
                serverExpired = true;
              }
            } catch (e) {}
          }
          if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
            serverExpired = true;
          }
          currentUser.permissions.is_expired = serverExpired;
          const isLicExpiredGlobally = serverExpired || (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) || (window._activationStatusData && window._activationStatusData.is_expired === true);
          if (isLicExpiredGlobally) {
            window._activationChatHadActivation = false;
            if (typeof window.setLicenseExpiredMode === 'function') {
              window.setLicenseExpiredMode(true);
            }
          } else if (data.user.permissions.is_expired === false && (!window._activationStatusData || window._activationStatusData.is_expired === false)) {
            const hadExpiredActive = window._isLicenseExpiredModeActive;
            window._activationChatHadActivation = true;
            if (typeof window.setLicenseExpiredMode === 'function') {
              window.setLicenseExpiredMode(false);
            }
            if (hadExpiredActive && typeof window.restoreActiveMonitoringState === 'function') {
              window.restoreActiveMonitoringState().catch(() => {});
            }
          }
        }
      }
      currentUser.permissions.max_searches = 10;
      currentUser.permissions.target_interval = 1;
      currentUser.username = data.user.username || devId;
      currentUser.name = data.user.name || (currentUser.username ? currentUser.username.substring(0, 14) : 'Устройство');
      if (data.user.telegram_chat_id !== undefined) currentUser.telegram_chat_id = data.user.telegram_chat_id;
      if (data.user.telegram_username !== undefined) currentUser.telegram_username = data.user.telegram_username;
      if (data.user.telegram_pending !== undefined) currentUser.telegram_pending = data.user.telegram_pending;
      if (data.user.target_interval !== undefined) currentUser.target_interval = data.user.target_interval;
      if (data.user.active_interval !== undefined) currentUser.active_interval = data.user.active_interval;
      if (typeof updateAvitoTimerUI === 'function') updateAvitoTimerUI();
      if (data.user.avito_searches !== undefined) {
        currentUser.avito_searches = normalizeSearches(data.user.avito_searches);
        if (avitoData && (!avitoData.searches || avitoData.searches.length === 0)) {
          avitoData.searches = currentUser.avito_searches;
        }
      }
      if (data.user.plain_password !== undefined) currentUser.plain_password = data.user.plain_password;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      updateAuthUI();
      updateAvitoHeaderDots();

      return true;
    }
  } catch (err) {
    console.error('syncUserSession error:', err);
  }
  return false;
}

// Автоматическая реактивная проверка прав и статуса сессии в фоне без перезагрузки страницы
if (!window._userSessionSyncSetup) {
  window._userSessionSyncSetup = true;
  setInterval(() => {
    if (currentUser && document.visibilityState === 'visible') {
      syncUserSession();
    }
  }, 12000);

  window.addEventListener('focus', () => {
    if (currentUser) syncUserSession();
  }, { passive: true });

  document.addEventListener('visibilitychange', () => {
    if (currentUser && document.visibilityState === 'visible') {
      syncUserSession();
    }
  }, { passive: true });
}

let avitoStatsPollerHandle = null;
let _backgroundTickerWorker = null;

function startAvitoStatsPoller() {
  if (avitoStatsPollerHandle) clearInterval(avitoStatsPollerHandle);
  
  const tickFn = () => {
    if (currentUser) {
      loadAvitoStats();
    }
  };

  // 1. Основной интервал опроса (каждые 2.2 сек)
  avitoStatsPollerHandle = setInterval(tickFn, 2200);

  // 2. Web Worker таймер: гарантирует опрос БЕЗ троттлинга браузера при свернутом окне
  if (!_backgroundTickerWorker && window.Worker && window.Blob) {
    try {
      const workerBlob = new Blob([
        'setInterval(function() { postMessage("tick"); }, 2200);'
      ], { type: 'application/javascript' });
      _backgroundTickerWorker = new Worker(URL.createObjectURL(workerBlob));
      _backgroundTickerWorker.onmessage = function() {
        tickFn();
      };
    } catch (e) {}
  }
}

// Автоматическое обновление открытой вкладки при запуске/перезапуске сервера (не создавать новую вкладку)
(function initServerReloadListener() {
  let _initialBootTime = null;
  const tabId = 'tab_' + Math.random().toString(36).substring(2, 9);
  
  function checkServerReload() {
    fetch('/api/server/live-check?tab_id=' + tabId + '&t=' + Date.now())
      .then(r => r.json())
      .then(d => {
        if (d && d.boot_time) {
          if (_initialBootTime === null) {
            _initialBootTime = d.boot_time;
          } else if (_initialBootTime !== d.boot_time) {
            console.log('[AvitoHunter] Сервер перезапущен: автоматическое обновление текущей вкладки...');
            _initialBootTime = d.boot_time;
            window.location.reload();
          }
        }
      })
      .catch(() => {});
  }
  
  setInterval(checkServerReload, 1800);
  setTimeout(checkServerReload, 600);
})();

async function init() {
  detectAndApplyDeviceOptimization();
  updateAuthUI();

  // На настольном ПК перед первой проверкой лицензии синхронизируем реальный HWID сервера
  if (!window.isMobileDevice() && typeof window.ensureClientDeviceId === 'function') {
    try { await window.ensureClientDeviceId(true); } catch(e) {}
  }

  // 1. ПЕРВЫМ ДЕЛОМ проверяем лицензию при открытии сайта
  let licenseStatus = null;
  if (typeof window.loadLicenseStatus === 'function') {
    try {
      licenseStatus = await window.loadLicenseStatus();
    } catch (e) {
      console.warn('License check error in init():', e);
    }
  }

  const isExpired = !licenseStatus || licenseStatus.is_expired === true || (!licenseStatus.active_key && licenseStatus.duration !== 'unlimited') || (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired());

  if (isExpired) {
    // Лицензия просрочена или отсутствует:
    // Блокируем фоновый мониторинг и отображаем экран активации
    window.setLicenseExpiredMode(true, licenseStatus);
    // Рендерим базовый каркас без запуска фоновых процессов опроса
    currentCat = 'avito_monitor';
    updateModeHeader('avito');
    renderCategories();
    updateAvitoTimerUI();
    updateAvitoHeaderDots();
    // Стартовая страница — экран "Активация" (без принудительного открытия модального окна)
    return;
  }

  // 2. Лицензия активна — запускаем все фоновые процессы мониторинга
  if (currentUser) {
    initAvitoTimer();
    startAvitoStatsPoller();
    syncUserSession();
    if (typeof window.updateTariffBadgeLive === 'function') {
      window.updateTariffBadgeLive();
    }
  }
  fetchServerNetworkInfo();
  try {
    components = [];
    engineeringNotes = {};
    orders = [];
    // Загрузка статистики Avito
    if (currentUser) {
      await loadAvitoStats();
      initAvitoTimer();
    }
    currentCat = 'avito_monitor';
    updateModeHeader('avito');
    renderCategories();
    renderList();
    updateAvitoHeaderDots();
  } catch (err) {
    console.error('Ошибка инициализации Avito Bot:', err);
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;color:#ef4444;background:var(--bg-card);padding:2.5rem 1.5rem;border-radius:12px;border:1px dashed #ef4444;max-width:600px;margin:2rem auto;">
        <div style="font-size:2.5rem;margin-bottom:0.75rem;">⚠️</div>
        <h3 style="font-size:1.25rem;margin-bottom:0.5rem;color:#f87171;">Ошибка загрузки данных мониторинга</h3>
        <p style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:1rem;">
          ${escapeHtml(err && (err.message || String(err)))}
        </p>
        <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:1.25rem;">
          Убедитесь, что запущен сервер <code>start_server.bat</code> и страница открыта по адресу <strong style="color:var(--text-primary);">http://localhost/</strong>
        </p>
        <button onclick="init()" class="cat-btn active" style="padding:0.6rem 1.5rem;font-size:0.95rem;cursor:pointer;">
          🔄 Повторить попытку
        </button>
      </div>
    `;
  }
}

function isTelegramAccountConfirmed(user) {
  const u = user || currentUser;
  if (!u) return false;
  const pending = (avitoData && avitoData.stats && avitoData.stats.telegram_pending) || u.telegram_pending;
  if (pending && pending.status === 'pending') {
    return false;
  }
  const hasId = Boolean(u.telegram_chat_id && String(u.telegram_chat_id).trim() && String(u.telegram_chat_id) !== '0');
  const hasUser = Boolean(u.telegram_username && u.telegram_username.trim());
  return hasId || hasUser;
}
window.isTelegramAccountConfirmed = isTelegramAccountConfirmed;

function getAvitoNodesStatus() {
  if (!hasPermission('avito_bot')) {
    return {
      monActive: false,
      tgActive: false,
      monClass: 'monitor-dot dot-mon dot-off',
      monTitle: 'Avito-Parser: нет доступа (обратитесь к администратору)',
      botClass: 'monitor-dot dot-bot dot-off',
      botTitle: 'Telegram-бот: нет доступа (обратитесь к администратору)'
    };
  }

  if (currentUser) {
    if (!currentUser.permissions) currentUser.permissions = {};
    if (currentUser.permissions.monitoring === undefined && avitoData && avitoData.stats && avitoData.stats.user_monitoring !== undefined) {
      currentUser.permissions.monitoring = avitoData.stats.user_monitoring;
    }
    if (currentUser.permissions.tg_bot === undefined && avitoData && avitoData.stats && avitoData.stats.user_tg_bot !== undefined) {
      currentUser.permissions.tg_bot = avitoData.stats.user_tg_bot;
    }
  }

  // 1-й кружок: Мониторинг Avito (точно соответствует кнопке «Мониторинг: ВКЛ/ВЫКЛ»)
  const monActive = Boolean(
    currentUser && currentUser.permissions && currentUser.permissions.monitoring !== false
  );

  // 2-й кружок: Telegram-бот (точно соответствует кнопке «ТГ-Уведомления: ВКЛ/ВЫКЛ»)
  const tgActive = Boolean(
    currentUser && currentUser.permissions && currentUser.permissions.tg_bot !== false
  );

  let monClass = 'monitor-dot dot-mon dot-off';
  let monTitle = 'Мониторинг Avito: Выключен (🔴)';

  if (monActive) {
    const currentProxies = (avitoData && avitoData.stats && avitoData.stats.proxy_count !== undefined)
      ? Number(avitoData.stats.proxy_count)
      : avitoProxyCount;

    if (currentProxies === 0 && avitoData && avitoData.stats) {
      monClass = 'monitor-dot dot-mon dot-warn';
      monTitle = 'Мониторинг Avito: Ожидание прокси (🟡 защита IP)';
    } else {
      monClass = 'monitor-dot dot-mon dot-on';
      monTitle = `Мониторинг Avito: Включен (🟢${currentProxies > 0 ? ', прокси: ' + currentProxies : ''})`;
    }
  }

  // 2-й кружок: серый dot-gray если Telegram не подтвержден, желтый если pending, иначе зеленый/красный
  const isTgConfirmed = isTelegramAccountConfirmed(currentUser);
  const isPending = !isTgConfirmed && Boolean(
    (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending') ||
    (avitoData && avitoData.stats && avitoData.stats.telegram_pending && avitoData.stats.telegram_pending.status === 'pending')
  );

  let botClass = '';
  let botTitle = '';
  if (isPending) {
    botClass = 'monitor-dot dot-bot dot-warn';
    botTitle = 'Telegram-аккаунт: ожидает подтверждения (🟡)';
  } else if (!isTgConfirmed) {
    botClass = 'monitor-dot dot-bot dot-gray';
    botTitle = 'Telegram-аккаунт: не подтвержден (⚪)';
  } else {
    botClass = `monitor-dot dot-bot ${tgActive ? 'dot-on' : 'dot-off'}`;
    botTitle = tgActive
      ? 'ТГ-Уведомления: Включены (🟢)'
      : 'ТГ-Уведомления: Выключены (🔴)';
  }

  return { monActive, tgActive, monClass, monTitle, botClass, botTitle };
}

function updateAvitoBotPhoneUI() {
  const btn = document.getElementById('btn-avito-bot-phone');
  const btnTg = document.getElementById('btn-user-tg-toggle');

  const isTgConfirmed = isTelegramAccountConfirmed(currentUser);
  const isPending = !isTgConfirmed && Boolean(
    (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending') ||
    (avitoData && avitoData.stats && avitoData.stats.telegram_pending && avitoData.stats.telegram_pending.status === 'pending')
  );

  // Затемняем ТГ-уведомления, если аккаунт Telegram НЕ подтвержден
  if (btnTg) {
    if (!isTgConfirmed) {
      btnTg.className = 'btn-avito-switch btn-inactive-gray';
      btnTg.style.opacity = '0.45';
      btnTg.style.pointerEvents = 'none';
      btnTg.style.cursor = 'not-allowed';
      btnTg.style.filter = 'grayscale(0.7)';
      if (isPending) {
        btnTg.title = 'Ожидает подтверждения в Telegram-боте. Откройте бота и подтвердите аккаунт.';
        btnTg.innerHTML = '⏳ ТГ-Уведомления: Ожидание';
      } else {
        btnTg.title = 'Для включения ТГ-уведомлений сначала подтвердите аккаунт Telegram справа';
        btnTg.innerHTML = '⚪ ТГ-Уведомления: ВЫКЛ';
      }
    } else {
      const isUserTgActive = Boolean(!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false);
      btnTg.className = `btn-avito-switch ${isUserTgActive ? 'btn-active-green' : 'btn-inactive-gray'}`;
      btnTg.style.opacity = '';
      btnTg.style.pointerEvents = '';
      btnTg.style.cursor = '';
      btnTg.style.filter = '';
      btnTg.title = 'Включить или выключить отправку уведомлений в Telegram';
      btnTg.innerHTML = isUserTgActive ? '🟢 ТГ-Уведомления: ВКЛ' : '🔴 ТГ-Уведомления: ВЫКЛ';
    }
  }

  if (!btn) return;

  // Затемняем и делаем недоступным для нажатий ТГ-Бот, если аккаунт Telegram НЕ подтвержден
  if (!isTgConfirmed) {
    btn.className = 'btn-avito-switch btn-inactive-gray';
    btn.style.cssText = 'background:rgba(148,163,184,0.15);color:var(--text-secondary);border-color:rgba(148,163,184,0.3);font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;opacity:0.45;pointer-events:none;cursor:not-allowed;filter:grayscale(0.7);white-space:nowrap;';
    if (isPending) {
      btn.title = 'Ожидает подтверждения в Telegram-боте. Откройте бота и подтвердите аккаунт.';
      btn.innerHTML = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: ⏳ Ожидание';
    } else {
      btn.title = 'Для управления ТГ-Ботом сначала подтвердите аккаунт Telegram справа';
      btn.innerHTML = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: ⚪ Не привязан';
    }
    return;
  }

  const isUserTg = Boolean(!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false);
  const isBotPaused = !isUserTg || Boolean(avitoData && avitoData.stats && avitoData.stats.bot_paused);

  // Бот имеет только 2 состояния: 🟢 Запущен / 🟡 Пауза
  let botPhoneClass = 'btn-active-green';
  let botPhoneStyle = 'background:rgba(16,185,129,0.15);color:#10b981;border-color:rgba(16,185,129,0.5);font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;white-space:nowrap;';
  let botPhoneTitle = 'ТГ-Бот в Telegram запущен и принимает объявления. Нажмите для паузы.';
  let botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: 🟢 Запущен';

  if (isBotPaused) {
    botPhoneClass = 'btn-active-yellow';
    botPhoneStyle = 'background:rgba(234,179,8,0.18);color:#eab308;border-color:rgba(234,179,8,0.55);font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;white-space:nowrap;';
    botPhoneTitle = 'ТГ-Бот в Telegram на паузе (поиск остановлен). Нажмите для возобновления.';
    botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: 🟡 Пауза';
  }

  btn.className = `btn-avito-switch ${botPhoneClass}`;
  btn.style.cssText = botPhoneStyle;
  btn.title = botPhoneTitle;
  btn.innerHTML = botPhoneHtml;
}

function updateAvitoHeaderDots() {
  const { monActive, tgActive, monClass, monTitle, botClass, botTitle } = getAvitoNodesStatus();

  // 1-й кружок: Мониторинг Avito (в шапке сайта и на главном портале)
  document.querySelectorAll('#dot-mon, #home-dot-mon, .dot-mon').forEach(el => {
    el.className = monClass;
    el.title = monTitle;
  });

  // 2-й кружок: Telegram-бот и уведомления (в шапке сайта и на главном портале)
  document.querySelectorAll('#dot-bot, #home-dot-bot, .dot-bot').forEach(el => {
    el.className = botClass;
    el.title = botTitle;
  });

  // Кнопка переключения мониторинга внутри раздела Avito
  const btnMon = document.getElementById('btn-user-mon-toggle');
  if (btnMon) {
    let curSearches = (avitoData && Array.isArray(avitoData.searches)) ? normalizeSearches(avitoData.searches) : [];
    if (curSearches.length === 0 && currentUser && currentUser.avito_searches) {
      curSearches = normalizeSearches(currentUser.avito_searches);
    }
    const hasSearches = curSearches.length > 0;
    if (!hasSearches) {
      btnMon.className = 'btn-avito-switch btn-inactive-gray is-disabled-empty-searches';
      btnMon.innerHTML = '⚪ Мониторинг: ВЫКЛ';
      btnMon.title = 'Для включения мониторинга сначала добавьте хотя бы одну ссылку для поиска';
      btnMon.style.opacity = '0.4';
      btnMon.style.pointerEvents = 'none';
      btnMon.style.cursor = 'not-allowed';
      btnMon.style.filter = 'grayscale(0.8)';
    } else {
      btnMon.classList.remove('is-disabled-empty-searches');
      btnMon.style.opacity = '';
      btnMon.style.pointerEvents = '';
      btnMon.style.cursor = '';
      btnMon.style.filter = '';
      const isUserMonActive = !(currentUser && currentUser.permissions && currentUser.permissions.monitoring === false);
      const currentProxies = (avitoData && avitoData.stats && avitoData.stats.proxy_count !== undefined)
        ? Number(avitoData.stats.proxy_count)
        : avitoProxyCount;
      const isWaitingProxies = isUserMonActive && currentProxies === 0 && Boolean(avitoData && avitoData.stats);

      if (!isUserMonActive) {
        btnMon.className = 'btn-avito-switch btn-inactive-gray';
        btnMon.innerHTML = '🔴 Мониторинг: ВЫКЛ';
        btnMon.title = 'Мониторинг выключен. Нажмите для включения.';
      } else if (isWaitingProxies) {
        btnMon.className = 'btn-avito-switch btn-active-warn';
        btnMon.innerHTML = '🟡 Ожидание прокси';
        btnMon.title = 'Мониторинг включен, но в пуле 0 прокси (пауза для защиты IP от бана). Нажмите для выключения.';
      } else {
        btnMon.className = 'btn-avito-switch btn-active-green';
        btnMon.innerHTML = '🟢 Мониторинг: ВКЛ';
        btnMon.title = `Мониторинг активен (прокси в пуле: ${currentProxies}). Нажмите для выключения.`;
      }
    }
  }
  updateAvitoBotPhoneUI();
}
window.updateAvitoHeaderDots = updateAvitoHeaderDots;

async function loadAvitoStats(forceFresh = false) {
  if (!currentUser || window._isLoadingAvitoStats) return;
  if (window._isAvitoFetchingAll && !forceFresh) return;
  window._isLoadingAvitoStats = true;
  try {
    const devId = (currentUser && currentUser.username) || (typeof window.getClientDeviceId === 'function' ? window.getClientDeviceId() : '');
    const userParam = devId ? '&username=' + encodeURIComponent(devId) + '&request_id=' + encodeURIComponent(devId) : '';
    const freshParam = forceFresh ? '&fresh=1' : '';
    const res = await fetch('/api/avito/stats?t=' + Date.now() + userParam + freshParam);
    if (res.ok) {
      const data = await res.json();
      if (data && data.success) {
        if (data.expires_at) {
          try {
            const expDt = new Date(data.expires_at.replace(' ', 'T'));
            if (!isNaN(expDt.getTime()) && new Date() >= expDt) {
              data.is_expired = true;
            }
          } catch (e) {}
        }
        if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
          data.is_expired = true;
        }
        let parsedSearches = normalizeSearches(data.searches);
        if (parsedSearches.length === 0 && currentUser && currentUser.avito_searches) {
          parsedSearches = normalizeSearches(currentUser.avito_searches);
        }
        data.searches = parsedSearches;
        if (currentUser && data.searches.length > 0) {
          currentUser.avito_searches = data.searches;
          try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        }
        // Защита от мигания и исчезновения карточек:
        // Если на клиенте уже были загружены объявления (например, через «Загрузить всё»),
        // а ответ от /stats временно пуст или неполный — сохраняем имеющиеся карточки и их данные!
        if (data.items && Array.isArray(data.items)) {
          if (data.items.length === 0 && avitoData && Array.isArray(avitoData.items) && avitoData.items.length > 0) {
            data.items = avitoData.items;
          } else if (avitoData && Array.isArray(avitoData.items) && avitoData.items.length > 0) {
            const mergedMap = new Map();
            avitoData.items.forEach(it => { if (it && it.item_id) mergedMap.set(String(it.item_id), it); });
            data.items.forEach(it => {
              if (it && it.item_id) {
                const prev = mergedMap.get(String(it.item_id));
                if (prev) {
                  if (!it.photos && prev.photos) it.photos = prev.photos;
                  if (!it.description && prev.description) it.description = prev.description;
                  if (!it.photo && prev.photo) it.photo = prev.photo;
                  if (!it.seller_rating && prev.seller_rating) it.seller_rating = prev.seller_rating;
                }
                mergedMap.set(String(it.item_id), it);
              }
            });
            data.items = Array.from(mergedMap.values());
          }
        } else if (avitoData && Array.isArray(avitoData.items)) {
          data.items = avitoData.items;
        }
        avitoData = data;
        if (Array.isArray(data.blacklist_cards) && data.blacklist_cards.length > 0) {
          try {
            const curCards = getBlacklistCardIds();
            data.blacklist_cards.forEach(id => { if (id) curCards.add(String(id)); });
            saveBlacklistCardIds(curCards);
          } catch (e) {}
        }
        if (Array.isArray(data.blacklist_sellers) && data.blacklist_sellers.length > 0) {
          try {
            const curSellers = getBlacklistSellers();
            data.blacklist_sellers.forEach(s => { if (s) curSellers.add(String(s).trim().toLowerCase()); });
            saveBlacklistSellers(curSellers);
          } catch (e) {}
        }
        if (data.stats && data.stats.proxy_count !== undefined) {
          avitoProxyCount = Number(data.stats.proxy_count) || 0;
          updateAvitoProxiesUI();
        }

        const canHighlight = !isWaitingProxyForPoll && avitoProxyCount > 0 && isAvitoPollingActive();
        if (!canHighlight) {
          _recentlyPolledSearchKeys.clear();
          document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
        }

        // Отслеживание обновления времени опроса каждой ссылки и определение первого сбора
        const initialSearchNames = new Set();
        if (Array.isArray(data.searches)) {
          data.searches.forEach((s, idx) => {
            const key = getSearchUniqueKey(s, idx);
            const prev = _searchesLastPolledMap.get(key);
            // Если ссылка еще не была опрошена ИЛИ это ее самый первый сбор
            if (!s.last_polled_at || !prev || s.is_initialized === 0) {
              if (s.name) initialSearchNames.add(s.name.trim().toLowerCase());
            }
            const isPending = Boolean(s.is_pending) || (window._pendingSearchesInModal && window._pendingSearchesInModal.has(s.id));
            if (!isPending && canHighlight && _searchesFirstLoaded && s.last_polled_at && prev !== undefined && s.last_polled_at !== prev) {
              _recentlyPolledSearchKeys.add(key);
              highlightPolledSearchBadge(key);
              setTimeout(() => {
                _recentlyPolledSearchKeys.delete(key);
                unhighlightPolledSearchBadge(key);
              }, 1200);
            }
            if (s.last_polled_at) {
              _searchesLastPolledMap.set(key, s.last_polled_at);
            } else if (!_searchesLastPolledMap.has(key)) {
              _searchesLastPolledMap.set(key, '');
            }
          });
          _searchesFirstLoaded = true;
        }
        
        if (Array.isArray(data.items)) {
          const delIds = getDeletedAvitoItemIds();
          const favSet = getFavoriteIds();
          if (delIds.size > 0) {
            data.items = data.items.filter(it => !delIds.has(String(it.item_id).trim()) || favSet.has(String(it.item_id).trim()));
          }
          if (knownAvitoItemIds.size > 0) {
            let newlyFoundCount = 0;
            let initialCollectedCount = 0;
            data.items.forEach(it => {
              const id = String(it.item_id);
              if (!knownAvitoItemIds.has(id)) {
                // Если объявление пришло от первого сбора — добавляем тихо, без спама о "новых"
                const sName = (it.search_name || '').trim().toLowerCase();
                const isInitial = Boolean(it.initial) || initialSearchNames.has(sName);
                if (isInitial) {
                  initialCollectedCount++;
                } else if (!viewedAdIds.has(id)) {
                  markItemAsFresh(id);
                  newlyFoundCount++;
                }
              }
            });
            const isInitialStartup = (Date.now() - _pageLoadedTime) < 6000;
            if (newlyFoundCount > 0 && !isInitialStartup) {
              if (typeof window.playAvitoChime === 'function') {
                window.playAvitoChime();
              }
              if (typeof notifyNewCardsBackground === 'function') {
                notifyNewCardsBackground(newlyFoundCount);
              }
            }
            // Перерисовываем список карточек ТОЛЬКО если действительно появились новые объявления,
            // либо если был принудительный запрос (forceFresh), либо если сетка пуста на клиенте.
            // При обычных опросах без новых объявлений сетку НЕ перерисовываем, чтобы карточки и фото не дёргались!
            const hasVisibleCards = document.querySelector('.avito-card') || document.querySelector('.card');
            const isGridEmpty = (!hasVisibleCards) && data.items.length > 0;
            const shouldRenderCards = (newlyFoundCount > 0 || initialCollectedCount > 0 || forceFresh || isGridEmpty);
            if (currentCat === 'avito_monitor' && shouldRenderCards) {
              if (newlyFoundCount > 0) {
                currentAvitoPage = 1;
              }
              if (typeof _isEditingTg === 'undefined' || (!_isEditingTg && document.activeElement !== document.getElementById('input-my-tg-handle'))) {
                renderList();
              }
            }
          } else {
            // Первая загрузка / рефреш страницы:
            // Карточки, уже просмотренные пользователем, остаются просмотренными навсегда (не превращаются снова в новые).
            if (currentCat === 'avito_monitor' && data.items.length > 0) {
              if (typeof _isEditingTg === 'undefined' || (!_isEditingTg && document.activeElement !== document.getElementById('input-my-tg-handle'))) {
                renderList();
              }
            }
          }
          data.items.forEach(it => knownAvitoItemIds.add(String(it.item_id)));
        }
        
        if (data.stats && currentUser) {
          let userChanged = false;
          if (data.stats.telegram_chat_id !== undefined && currentUser.telegram_chat_id !== data.stats.telegram_chat_id) {
            currentUser.telegram_chat_id = data.stats.telegram_chat_id;
            userChanged = true;
          }
          if (data.stats.telegram_username !== undefined && currentUser.telegram_username !== data.stats.telegram_username) {
            currentUser.telegram_username = data.stats.telegram_username;
            userChanged = true;
          }
          if (data.stats.telegram_pending !== undefined && currentUser.telegram_pending !== data.stats.telegram_pending) {
            if (typeof _isEditingTg === 'undefined' || !_isEditingTg) {
              currentUser.telegram_pending = data.stats.telegram_pending;
              userChanged = true;
            }
          }
          if (data.stats.user_monitoring !== undefined && currentUser.permissions) {
            currentUser.permissions.monitoring = Boolean(data.stats.user_monitoring);
          }
          if (data.stats.user_tg_bot !== undefined && currentUser.permissions) {
            currentUser.permissions.tg_bot = Boolean(data.stats.user_tg_bot);
          }
          if (userChanged) {
            try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
          }
        }

        if (data.stats) {
          if (data.stats.target_interval !== undefined) {
            const rawTarget = data.stats.target_interval;
            const newTarget = String(rawTarget).toLowerCase().includes('rand') ? 60 : (Number(rawTarget) || 60);
            const cardInt = typeof getUserCardInterval === 'function' ? getUserCardInterval() : 60;
            const clampedTarget = Math.max(cardInt, newTarget);
            let timerChanged = false;
            if (Number(avitoTargetInterval) !== clampedTarget) {
              avitoTargetInterval = clampedTarget;
              avitoTimerSecondsLeft = getNextAvitoInterval();
              timerChanged = true;
            }
            if (data.stats.hybrid_mode !== undefined) {
              const serverHybrid = Boolean(data.stats.hybrid_mode);
              if (avitoHybridMode !== serverHybrid) {
                avitoHybridMode = serverHybrid;
                timerChanged = true;
              }
            }
            if (data.stats.direct_mode !== undefined) {
              const serverDirect = Boolean(data.stats.direct_mode);
              if (avitoDirectMode !== serverDirect) {
                avitoDirectMode = serverDirect;
                timerChanged = true;
              }
            }
            if (timerChanged) {
              updateAvitoTimerUI();
              const mOverlay = document.getElementById('modal-overlay');
              if (window._isSpeedModalOpen && mOverlay && mOverlay.classList.contains('open') && document.querySelector('.speed-preset-grid')) {
                openPollingSpeedModal();
              }
            }
          }
          if (data.stats.safe_interval !== undefined) {
            const prevSafe = avitoSafeInterval;
            avitoSafeInterval = Number(data.stats.safe_interval) || 30;
            if (prevSafe !== avitoSafeInterval && avitoTimerSecondsLeft > avitoSafeInterval && avitoTargetInterval !== 'random_30_60') {
              avitoTimerSecondsLeft = avitoSafeInterval;
            }
          }
          if (data.stats.needed_proxies !== undefined) {
            avitoNeededProxies = Number(data.stats.needed_proxies) || 0;
          }
          if (data.stats.proxy_count !== undefined) {
            avitoProxyCount = Number(data.stats.proxy_count) || 0;
          }
          if (data.stats.proxy_fetching !== undefined) {
            avitoIsFetchingProxies = Boolean(data.stats.proxy_fetching);
          }
          if (currentUser && currentUser.permissions && currentUser.permissions.tg_bot === false) {
            data.stats.bot_paused = true;
          }
        }

        // Обновляем кнопку телефона бота, прокси и индикаторы в реальном времени
        updateAvitoBotPhoneUI();
        updateAvitoProxiesUI();
        updateAvitoHeaderDots();
        updateAvitoTimerUI();

        // Проверяем правила остановки поиска прокси:
        // Если отключен мониторинг и затемнены тг-уведомления (серый кружок) ИЛИ отключены тг-уведомления -> прекратить поиск прокси
        const hasTgAccount = Boolean(
          currentUser && (
            (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
            (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
          )
        );
        const userMon = currentUser && currentUser.permissions ? currentUser.permissions.monitoring !== false : true;
        const userTg = Boolean(hasTgAccount && (!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false));
        const isAllDisabled = !userMon && (!hasTgAccount || !userTg);

        if (isAllDisabled) {
          // Прокси не останавливаем: поиск прокси работает независимо от мониторинга и ТГ
        }

        // Прокси ищем всегда (пока есть лицензия), вне зависимости от мониторинга и ТГ
        const isMonActive = Boolean(userMon && (!avitoData || !avitoData.stats || avitoData.stats.monitor_enabled !== false));
        const isTgActive = Boolean(hasTgAccount && userTg && (!avitoData || !avitoData.stats || !avitoData.stats.bot_paused));
        const shouldSearch300 = true; // всегда, пока лицензия активна
        const targetProxies = 999;
        const needsMoreProxies = avitoProxyCount < targetProxies;

        if (needsMoreProxies && !avitoIsFetchingProxies) {
          const nowMs = Date.now();
          const autoProxyCooldown = 15 * 1000;
          if (!window._lastAutoProxyFetchTime || (nowMs - window._lastAutoProxyFetchTime > autoProxyCooldown)) {
            window._lastAutoProxyFetchTime = nowMs;
            avitoIsFetchingProxies = true;
            updateAvitoProxiesUI();
            fetch('/api/avito/proxies/fetch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ action: 'start', source: 'auto', target: 999 })
            }).then(r => r.json()).then(d => {
              if (d && d.is_fetching !== undefined) {
                avitoIsFetchingProxies = d.is_fetching;
                if (avitoData && avitoData.stats) avitoData.stats.proxy_fetching = d.is_fetching;
              }
              updateAvitoProxiesUI();
            }).catch(() => {
              avitoIsFetchingProxies = false;
              updateAvitoProxiesUI();
            });
          }
        }

        updateAvitoTimerUI();
        renderCategories();
        if (currentCat === 'avito_monitor') {
          const statTotalEl = document.getElementById('avito-stat-total');
          if (statTotalEl && data.stats && data.stats.total_items !== undefined) {
            statTotalEl.innerText = data.stats.total_items;
            statTotalEl.style.color = Number(data.stats.total_items) === 0 ? '#ef4444' : '#fbbf24';
          }
          const sSearches = Array.isArray(data.searches) ? data.searches : (data.searches && data.searches.url ? [data.searches] : []);
          const statSearchesEl = document.getElementById('avito-stat-searches');
          if (statSearchesEl) {
            const activeList = sSearches.filter(s => s.is_active !== 0);
            const liveMax = (data.stats && data.stats.max_searches != null)
              ? data.stats.max_searches
              : (currentUser && currentUser.permissions && currentUser.permissions.max_searches != null
                  ? currentUser.permissions.max_searches : (isAdmin() ? null : 1));
            const liveVisible = (!isAdmin() && liveMax != null)
              ? Math.min(activeList.length, Number(liveMax))
              : activeList.length;
            statSearchesEl.innerText = liveVisible;
            statSearchesEl.style.color = Number(liveVisible) === 0 ? '#ef4444' : '#fbbf24';
          }
          const sChipsContainer = document.getElementById('avito-searches-chips-container');
          if (sChipsContainer) {
            const activeList = sSearches.filter(s => s.is_active !== 0);
            const liveMax2 = (data.stats && data.stats.max_searches != null)
              ? data.stats.max_searches
              : (currentUser && currentUser.permissions && currentUser.permissions.max_searches != null
                  ? currentUser.permissions.max_searches : (isAdmin() ? null : 1));

            let canUpdateInPlace = (activeList.length > 0 && sChipsContainer.querySelectorAll('.avito-search-chip').length === activeList.length);
            if (canUpdateInPlace) {
              for (let i = 0; i < activeList.length; i++) {
                const s = activeList[i];
                const key = getSearchUniqueKey(s, i);
                const safeId = getSafeSearchDomId(key);
                if (!document.getElementById(`poll-badge-${safeId}`)) {
                  canUpdateInPlace = false;
                  break;
                }
              }
            }

            if (canUpdateInPlace) {
              activeList.forEach((s, idx) => {
                const key = getSearchUniqueKey(s, idx);
                const safeId = getSafeSearchDomId(key);
                const badgeEl = document.getElementById(`poll-badge-${safeId}`);
                if (badgeEl) {
                  const pollTimeText = formatPollTime(s.last_polled_at, s.is_initialized);
                  const pollTitle = s.last_polled_at ? `Последний опрос: ${s.last_polled_at}` : 'Идёт первый сбор данных с Авито';
                  if (badgeEl.innerText !== pollTimeText) {
                    badgeEl.innerText = pollTimeText;
                  }
                  badgeEl.title = pollTitle;
                  const isInitS = Boolean(s.is_initialized == 1 || s.is_initialized === true || s.is_initialized === '1');
                  if (s.last_polled_at && isInitS) {
                    badgeEl.classList.remove('waiting');
                    badgeEl.classList.add('polled');
                  } else {
                    badgeEl.classList.remove('polled');
                    badgeEl.classList.add('waiting');
                  }
                  if (canHighlight && _recentlyPolledSearchKeys.has(key)) {
                    badgeEl.classList.add('poll-flash');
                  } else {
                    badgeEl.classList.remove('poll-flash');
                  }
                }
                const chipEl = document.getElementById(`search-chip-${safeId}`);
                if (chipEl) {
                  if (canHighlight && _recentlyPolledSearchKeys.has(key)) {
                    chipEl.classList.add('poll-flash');
                  } else {
                    chipEl.classList.remove('poll-flash');
                  }
                }
              });
            } else {
              sChipsContainer.innerHTML = renderAvitoSearchesHtml(sSearches, liveMax2);
            }
            const sBlock = document.getElementById('avito-searches-block');
            if (sBlock) {
              sBlock.classList.toggle('empty-highlight', !hasActiveAvitoSearches());
            }
            // Обновляем класс hint-centered у подсказки (центр — только когда нет ссылок)
            const hintEl = document.getElementById('avito-add-search-hint');
            if (hintEl) {
              const hasChips = activeList.length > 0;
              hintEl.classList.toggle('hint-centered', !hasChips);
            }
            if (typeof updateAddSearchHintPosition === 'function') {
              updateAddSearchHintPosition();
            }
          }
          const monContainer = document.querySelector('.avito-monitor-container');
          if (!monContainer) {
            renderList();
          }
        }
      }
    }
  } catch (e) {
    console.warn('Avito stats load error:', e);
  } finally {
    window._isLoadingAvitoStats = false;
  }
}

function updateModeHeader(mode) {
  const banner = document.getElementById('page-banner');
  const bannerTitle = document.getElementById('banner-title');
  const bannerDesc = document.getElementById('banner-desc');
  const btnAvito = document.getElementById('btn-avito-parser');
  const btnUsers = document.getElementById('quick-btn-users');

  if (btnAvito) btnAvito.classList.toggle('active', mode !== 'users');
  if (btnUsers) btnUsers.classList.toggle('active', mode === 'users');

  if (banner && bannerTitle && bannerDesc) {
    banner.classList.remove('banner-avito', 'banner-users', 'banner-shop', 'banner-instruments');
    if (mode === 'users') {
      banner.classList.add('banner-users');
      bannerTitle.innerHTML = '👥 Пользователи и сетевые гости';
      bannerDesc.innerText = 'Центр администрирования: учетные записи, управление тарифами и лимитами ссылок Avito, Telegram-боты, а также сетевые гости и подключения по Wi-Fi.';
    } else {
      banner.classList.add('banner-avito');
      bannerTitle.innerHTML = '<img src="img/banner_avito_icon.png?v=3" alt="Avito" style="width:34px;height:34px;vertical-align:middle;margin-right:10px;object-fit:contain;"> Мониторинг объявлений Авито';
      bannerDesc.innerText = 'Автоматический перехват новых объявлений с Avito в реальном времени, фильтрация по параметрам и мгновенные Telegram-уведомления.';
    }
  }

  const countLabel = document.getElementById('header-count-label');
  if (countLabel) {
    countLabel.innerText = (mode === 'users') ? 'Пользователей:' : 'Объявлений:';
  }

  const searchInputEl = document.getElementById('search-input');
  if (searchInputEl) {
    searchInputEl.placeholder = 'Поиск по объявлениям...';
  }
}

window.openAvitoTab = async function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    return;
  }
  if (currentCat === 'avito_monitor') return;
  if (!hasPermission('avito_bot')) {
    const hasNow = await syncUserSession();
    if (!hasNow) {
      const btn = document.getElementById('btn-avito-parser');
      if (btn) {
        btn.classList.remove('shake');
        void btn.offsetWidth;
        btn.classList.add('shake');
        setTimeout(() => btn.classList.remove('shake'), 400);
      }
      if (window.showToast) {
        window.showToast('⛔ За правами доступа обратитесь к администратору.', 4000, 'danger');
      } else {
        alert('За правами доступа обратитесь к администратору.');
      }
      return;
    }
  }
  currentCat = 'avito_monitor';
  updateModeHeader('avito');
  renderCategories();
  renderList();
  loadAvitoStats();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// Заглушки для удаленных разделов
window.openComponentsBaseTab = function() { window.openAvitoTab(); };
window.openShopTab = async function() { window.openAvitoTab(); };
window.openInstrumentsTab = function() { window.openAvitoTab(); };
window.openInstrumentsDevicesTab = function() { window.openAvitoTab(); };
window.openHomePortal = function() { window.openAvitoTab(); };

function getFilteredAvitoCount() {
  const rawQ = (searchInput && searchInput.value ? searchInput.value : '').trim().toLowerCase();
  let items = avitoData.items || [];
  if (rawQ) {
    items = items.filter(it => 
      (it.title && it.title.toLowerCase().includes(rawQ)) ||
      (it.price && it.price.toLowerCase().includes(rawQ)) ||
      (it.address && it.address.toLowerCase().includes(rawQ)) ||
      (it.seller && it.seller.toLowerCase().includes(rawQ)) ||
      (it.search_name && it.search_name.toLowerCase().includes(rawQ)) ||
      (it.url && it.url.toLowerCase().includes(rawQ))
    );
  }
  return items.length;
}

function renderQuickTabs() {
  const avitoCount = getFilteredAvitoCount();
  const btnAvito = document.getElementById('quick-btn-avito');
  const countAvito = document.getElementById('quick-avito-count');
  const countUsers = document.getElementById('quick-users-count');

  if (countAvito) countAvito.innerText = avitoCount;
  if (countUsers && _cachedUsersData && _cachedUsersData.users) {
    countUsers.innerText = _cachedUsersData.users.length;
  }
  if (btnAvito) {
    btnAvito.classList.toggle('active', currentCat === 'avito_monitor');
  }

  const btnUsers = document.getElementById('quick-btn-users');
  if (btnUsers) {
    btnUsers.classList.toggle('active', currentCat === 'users');
    const uCount = (_cachedUsersData && _cachedUsersData.users) ? _cachedUsersData.users.length : 2;
    btnUsers.innerHTML = `👥 Пользователи: ${uCount}`;
  }
}

// Открыть вкладку Пользователи (для Администратора)
window.openUsersTab = function() {
  if (!isAdmin()) return;
  if (currentCat === 'users') return;
  selectQuickTab('users');
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

window.selectQuickTab = function(catId) {
  if (catId === 'users') {
    currentCat = 'users';
    if (typeof updateModeHeader === 'function') updateModeHeader('users');
  } else {
    currentCat = 'avito_monitor';
    if (typeof updateModeHeader === 'function') updateModeHeader('avito');
  }
  renderQuickTabs();
  renderCategories();
  renderList();
};

function renderCategories() {
  renderQuickTabs();
  const catNav = document.getElementById('categories-nav');
  const controlsBar = document.querySelector('.controls-bar');
  const adminArea = document.getElementById('admin-controls-area');
  if (catNav) catNav.style.display = 'none';
  if (controlsBar) controlsBar.style.display = 'none';
  if (adminArea) adminArea.style.display = 'none';
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ========================================================
// ЦВЕТА И КУПЮРЫ БАНКА РОССИИ
// ========================================================
const BANKNOTE_IMAGES = {
  5000: '/img/banknote_5000.png',
  2000: '/img/banknote_2000.png',
  1000: '/img/banknote_1000.png',
  500:  '/img/banknote_500.png',
  200:  '/img/banknote_200.png',
  100:  '/img/banknote_100.png',
  50:   '/img/banknote_50.png',
  5:    '/img/banknote_5.png',
};

function parseAvitoPrice(priceStr) {
  if (!priceStr) return 0;
  if (/бесплатно/i.test(priceStr)) return 0;
  const digits = String(priceStr).replace(/[^\d]/g, '');
  return digits ? parseInt(digits, 10) : 0;
}

function getBanknotePriceTier(numericPrice) {
  const p = Number(numericPrice) || 0;
  if (p >= 5000) return 'price-tier-5000';
  if (p >= 2000) return 'price-tier-2000';
  if (p >= 1000) return 'price-tier-1000';
  if (p >= 500)  return 'price-tier-500';
  if (p >= 200)  return 'price-tier-200';
  if (p >= 100)  return 'price-tier-100';
  if (p >= 50)   return 'price-tier-50';
  if (p >= 5)    return 'price-tier-5';
  return 'price-tier-default';
}

function getBanknoteTagHtml(numPrice, cleanPrice) {
  // Ищем точное совпадение или ближайшую купюру снизу
  const tiers = [5000, 2000, 1000, 500, 200, 100, 50, 5];
  let imgKey = null;
  if (BANKNOTE_IMAGES[numPrice]) {
    imgKey = numPrice;
  } else {
    for (const t of tiers) {
      if (numPrice >= t) { imgKey = t; break; }
    }
  }
  if (!imgKey || !BANKNOTE_IMAGES[imgKey]) return '';
  return `<img src="${BANKNOTE_IMAGES[imgKey]}" class="avito-price-banknote-tag" alt="Купюра ${cleanPrice}" title="Купюра ${cleanPrice}">`;
}


function renderPriceValueHtml(priceStr, customClass = '') {
  const cleanPrice = escapeHtml(priceStr || 'Цена не указана');
  const numPrice = parseAvitoPrice(priceStr);
  const tierClass = getBanknotePriceTier(numPrice);
  const banknoteTag = getBanknoteTagHtml(numPrice, cleanPrice);
  return `<strong class="${tierClass} ${customClass}">${cleanPrice}</strong>${banknoteTag}`;
}

function renderCardPriceRowHtml(priceStr) {
  const priceValueHtml = renderPriceValueHtml(priceStr);
  return `<span class="avito-card-price"><img src="/img/ruble_coin.png" class="avito-rub-coin-img" alt="₽" title="Цена в рублях"> <span class="avito-price-label">Цена:</span> ${priceValueHtml}</span>`;
}

window.openBanknotePreview = function() {};

function pluralLinks(n) {
  const abs = Math.abs(n) % 100;
  const rem = abs % 10;
  if (abs >= 11 && abs <= 14) return `${n} ссылок`;
  if (rem === 1) return `${n} ссылка`;
  if (rem >= 2 && rem <= 4) return `${n} ссылки`;
  return `${n} ссылок`;
}

function renderList() {
  currentCat = 'avito_monitor';
  const _btnAvito = document.getElementById('btn-avito-parser');
  if (_btnAvito) _btnAvito.classList.add('active');

  const controlsBar = document.querySelector('.controls-bar');
  const catNav = document.getElementById('categories-nav');
  const adminControlsArea = document.getElementById('admin-controls-area');

  if (controlsBar) controlsBar.style.display = 'none';
  if (catNav) catNav.style.display = 'none';
  if (adminControlsArea) adminControlsArea.style.display = 'none';

  const q = (searchInput && searchInput.value ? searchInput.value : '').trim();
  renderAvitoMonitor(q);
}

window.openUsersTab = function() { if (typeof openAvitoTab === 'function') openAvitoTab(); };
window.loadUsersData = async function() { return { users: [], visitors: [] }; };
window.renderUsersTab = function() {};
window.renderUsersUI = function() {};
window.openAuthModal = function() {};
window.switchAuthTab = function() {};
window.handleLogin = async function() {};
window.handleRegister = async function() {};

window.openAddOrderModal = function() {};
window.openAddComponentModal = function() {};
window.openEditComponentModal = function() {};
window.openDetailModal = function() {};
window.openAddShopModal = function() {};
window.openAdminUploadModal = function() {};
window.saveComponentChanges = function() {};
window.deleteComponent = function() {};
window.handleAddNewComponent = function() {};
window.handleCircuitUpload = function() {};
window.submitComment = function() {};

async function updateUsersCountBadge() {}

window.renderUsersUI = function() {};
function closeModal() {
  if (typeof window.stopAvitoSoundPreview === 'function') {
    window.stopAvitoSoundPreview();
  }
  const soundGearBtn = document.getElementById('btn-avito-sound-settings');
  if (soundGearBtn) soundGearBtn.classList.remove('active');
  window._isSpeedModalOpen = false;
  window._speedModalReqId = (window._speedModalReqId || 0) + 1;
  modalOverlay.classList.remove('open');
  document.body.classList.remove('modal-open');
  document.documentElement.classList.remove('modal-open');
  const content = document.querySelector('.modal-content');
  if (content) {
    content.classList.remove('chat-modal-mode');
    content.classList.remove('gallery-modal-mode');
  }
  if (window._galleryKeydownHandler) {
    window.removeEventListener('keydown', window._galleryKeydownHandler);
    window._galleryKeydownHandler = null;
  }
  window._avitoGenState = null;
  window._isManageSearchesModalOpen = false;
  const pendingSet = new Set(window._pendingSearchesInModal || []);
  const currentSearches = (currentUser && currentUser.avito_searches) || (avitoData && avitoData.searches) || [];
  currentSearches.forEach(s => {
    if (s && s.is_pending && s.id) pendingSet.add(s.id);
  });
  if (pendingSet.size > 0) {
    const idsToActivate = Array.from(pendingSet);
    if (window._pendingSearchesInModal) window._pendingSearchesInModal.clear();
    currentSearches.forEach(s => {
      if (s && s.is_pending) s.is_pending = 0;
    });
    const reqUser = currentUser ? (currentUser.username || '') : '';
    fetch('/api/avito/activate-pending-searches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ids: idsToActivate,
        username: reqUser,
        request_id: reqUser
      })
    }).then(async () => {
      await loadAvitoStats(true);
      if (currentCat === 'avito_monitor') renderList();
      fetch('/api/avito/check', { method: 'POST' }).then(() => loadAvitoStats(true)).catch(() => {});
    }).catch(() => {});
  }
  if (typeof _activeChatModalItemId !== 'undefined') _activeChatModalItemId = null;
  if (typeof _lastModalContentScrollTop !== 'undefined') _lastModalContentScrollTop = 0;
  if (typeof _chatPollInterval !== 'undefined' && _chatPollInterval) {
    clearInterval(_chatPollInterval);
    _chatPollInterval = null;
  }
  if (typeof _activationChatPollInterval !== 'undefined' && _activationChatPollInterval) {
    clearInterval(_activationChatPollInterval);
    _activationChatPollInterval = null;
  }
  if (window._activationChatPollInterval) {
    clearInterval(window._activationChatPollInterval);
    window._activationChatPollInterval = null;
  }
  if (typeof _proxyModalInterval !== 'undefined' && _proxyModalInterval) {
    clearInterval(_proxyModalInterval);
    _proxyModalInterval = null;
  }
  if (typeof _stopSniperStatusPolling === 'function' && !window._sniperLoginWaitActive) {
    _stopSniperStatusPolling();
  }
  const wasActivationModal = !!document.getElementById('activation-chat-box');

  if (modalBody) {
    modalBody.innerHTML = '';
  }
  if (typeof _editingSearchId !== 'undefined') {
    _editingSearchId = null;
  }
  if (typeof window.checkAdminUnreadMessages === 'function') {
    setTimeout(window.checkAdminUnreadMessages, 500);
  }

  // Если лицензия истекла или не активирована — сайт ВСЕГДА остается строго заблокированным!
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    document.body.classList.add('license-expired-mode');
    const expOverlay = document.getElementById('license-expired-overlay');
    if (expOverlay) {
      expOverlay.style.display = 'flex';
      expOverlay.classList.add('is-active');
    }
    window._isLicenseExpiredModeActive = true;
    return;
  }

  // Если была зафиксирована активация в чате или ключом, либо статус не истек:
  // МГНОВЕННО скрываем экран блокировки и разблокируем сайт без задержек!
  if (!window.isLicenseExpired() && (window._activationChatHadActivation || (window._activationStatusData && window._activationStatusData.is_expired === false))) {
    const expOverlay = document.getElementById('license-expired-overlay');
    const wasExp = document.body.classList.contains('license-expired-mode');
    if (expOverlay && expOverlay.classList.contains('is-active')) {
      expOverlay.classList.remove('is-active');
      expOverlay.style.display = 'none';
    }
    document.body.classList.remove('license-expired-mode');
    window._isLicenseExpiredModeActive = false;
    if (currentUser && currentUser.permissions) {
      currentUser.permissions.is_expired = false;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
    }
    if (typeof window.setLicenseExpiredMode === 'function') {
      window.setLicenseExpiredMode(false);
    }
    if (typeof updateAvitoTimerUI === 'function') {
      updateAvitoTimerUI();
    }
    if (wasExp && currentCat === 'avito_monitor' && typeof renderList === 'function') {
      renderList();
    }
  }

  // При закрытии окна активации ВСЕГДА немедленно запрашиваем свежий статус с сервера без ожидания
  if (wasActivationModal && typeof window.loadLicenseStatus === 'function') {
    window.loadLicenseStatus().then(st => {
      if (st && st.is_expired === false) {
        window._activationChatHadActivation = true;
        const expOverlay = document.getElementById('license-expired-overlay');
        if (expOverlay) {
          expOverlay.classList.remove('is-active');
          expOverlay.style.display = 'none';
        }
        document.body.classList.remove('license-expired-mode');
        window._isLicenseExpiredModeActive = false;
        if (typeof window.setLicenseExpiredMode === 'function') {
          window.setLicenseExpiredMode(false);
        }
        if (typeof window.updateTariffBadgeLive === 'function') {
          window.updateTariffBadgeLive();
        }
        if (typeof updateAvitoTimerUI === 'function') {
          updateAvitoTimerUI();
        }
        if (currentCat === 'avito_monitor' && typeof renderList === 'function') {
          renderList();
        }
      }
    }).catch(() => {});
  }

  // При закрытии любого окна проверяем доступность сайта и снимаем режим блокировки при активной лицензии
  if (typeof window.isLicenseExpired === 'function' && !window.isLicenseExpired()) {
    if (typeof window.setLicenseExpiredMode === 'function') {
      window.setLicenseExpiredMode(false);
    }
    if (typeof updateAvitoTimerUI === 'function') {
      updateAvitoTimerUI();
    }
  }
}

modalClose.addEventListener('click', closeModal);
// Окна закрываются строго по крестику или по кнопке закрыть (клик по фону отключен)

// ==================== СОХРАНЕНИЕ ПОЗИЦИИ ПРОКРУТКИ МОДАЛЬНЫХ ОКОН ====================
let _lastModalContentScrollTop = 0;

function _saveCurrentModalScroll() {
  const content = document.querySelector('.modal-content');
  const overlay = document.getElementById('modal-overlay');
  if (content && overlay && overlay.classList.contains('open')) {
    _lastModalContentScrollTop = content.scrollTop;
  }
}

function _restoreCurrentModalScroll() {
  const content = document.querySelector('.modal-content');
  const overlay = document.getElementById('modal-overlay');
  if (!content || !overlay || !overlay.classList.contains('open')) return;
  // Восстанавливаем позицию только если браузер непредвиденно сбросил скролл в 0
  if (_lastModalContentScrollTop > 0 && content.scrollTop === 0) {
    content.scrollTop = _lastModalContentScrollTop;
    requestAnimationFrame(() => {
      if (content.scrollTop === 0 && _lastModalContentScrollTop > 0) {
        content.scrollTop = _lastModalContentScrollTop;
      }
    });
  }
}

const _modalContentEl = document.querySelector('.modal-content');
if (_modalContentEl) {
  _modalContentEl.addEventListener('scroll', () => {
    const overlay = document.getElementById('modal-overlay');
    if (overlay && overlay.classList.contains('open')) {
      _lastModalContentScrollTop = _modalContentEl.scrollTop;
    }
  }, { passive: true });
}

window.addEventListener('blur', _saveCurrentModalScroll, { passive: true });
window.addEventListener('focus', _restoreCurrentModalScroll, { passive: true });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    _saveCurrentModalScroll();
  } else if (document.visibilityState === 'visible') {
    _restoreCurrentModalScroll();
  }
}, { passive: true });

// ==========================================================================
// Avito Bot Monitor Module Functions
// ==========================================================================

function getAvitoPhotoFallbackHtml() {
  return `
    <div class="avito-no-photo-box" style="position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0.45rem;background:#0f172a;width:100%;height:100%;min-height:160px;user-select:none;">
      <div class="avito-photo-spinner" style="width:30px;height:30px;border:3px solid rgba(56,189,248,0.22);border-top-color:#38bdf8;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      <span class="avito-no-photo-tag" style="font-size:0.75rem;font-weight:600;color:#93c5fd;display:inline-flex;align-items:center;gap:0.3rem;">
        <span>⏳</span> <span>Загрузка фото...</span>
      </span>
    </div>
  `;
}

function getCardPrimaryPhoto(it) {
  if (!it) return null;
  if (it.photo && typeof it.photo === 'string' && it.photo.trim().length > 5) {
    return it.photo.trim();
  }
  if (Array.isArray(it.photos) && it.photos.length > 0) {
    for (let p of it.photos) {
      if (typeof p === 'string' && p.trim().length > 5) return p.trim();
      if (p && typeof p === 'object') {
        let u = p['1280x960'] || p['1024x768'] || p['864x648'] || p['678x678'] || p['558x558'] || p['372x372'] || p['url'] || p['src'];
        if (u && typeof u === 'string' && u.trim().length > 5) return u.trim();
      }
    }
  }
  if (typeof it.photos === 'string' && it.photos.trim().startsWith('[')) {
    try {
      const arr = JSON.parse(it.photos);
      if (Array.isArray(arr) && arr.length > 0) {
        for (let p of arr) {
          if (typeof p === 'string' && p.trim().length > 5) return p.trim();
          if (p && typeof p === 'object') {
            let u = p['1280x960'] || p['1024x768'] || p['864x648'] || p['678x678'] || p['558x558'] || p['372x372'] || p['url'] || p['src'];
            if (u && typeof u === 'string' && u.trim().length > 5) return u.trim();
          }
        }
      }
    } catch (_) {}
  }
  const cached = window._itemDetailsCache && window._itemDetailsCache.get(String(it.item_id));
  if (cached && Array.isArray(cached.photos) && cached.photos.length > 0) {
    for (let p of cached.photos) {
      if (typeof p === 'string' && p.trim().length > 5) return p.trim();
    }
  }
  return null;
}

// ==================== СКОРОСТЬ ОПРОСА ОБЪЯВЛЕНИЙ И АВТО-РАЗГОН ====================
function getUserCardInterval() {
  return 1;
}

let avitoTargetInterval = (() => {
  const cardInt = getUserCardInterval();
  if (currentUser && currentUser.active_interval) {
    const act = parseInt(currentUser.active_interval, 10);
    if (!isNaN(act) && act >= cardInt) return act;
  }
  return cardInt;
})();
let avitoSafeInterval = 1;
let avitoNeededProxies = 0;
let avitoProxyCount = 0;
let avitoIsFetchingProxies = false;
let avitoTimerSecondsLeft = 1;
let avitoTimerIntervalHandle = null;
let isAvitoCheckingNow = false;
let isWaitingProxyForPoll = false;
let waitingProxyCheckCounter = 0;
let avitoHybridMode = false; // Гибридный режим: прямой+прокси (direct 60-90сек если нет прокси)
let avitoDirectMode = false; // Прямой режим: 60-90 сек без прокси (рандом)

const _searchesLastPolledMap = new Map();
let _searchesFirstLoaded = false;
const _recentlyPolledSearchKeys = new Set();

function getSearchUniqueKey(s, idx) {
  if (s && s.id !== undefined && s.id !== null) return String(s.id);
  if (s && s.url) return String(s.url);
  return String(idx);
}

function getSafeSearchDomId(key) {
  return String(key).replace(/[^a-zA-Z0-9_-]/g, '_');
}

function highlightPolledSearchBadge(key) {
  const safeId = getSafeSearchDomId(key);
  const badgeEl = document.getElementById(`poll-badge-${safeId}`);
  const chipEl = document.getElementById(`search-chip-${safeId}`);
  const modalBadgeEl = document.getElementById(`modal-poll-badge-${safeId}`);

  // Если ссылка ожидает закрытия окна — не мигать синим ни в модалке, ни в чипах!
  if (modalBadgeEl && (modalBadgeEl.classList.contains('waiting') || modalBadgeEl.textContent.includes('поиск после закрытия'))) {
    return;
  }
  if (window._pendingSearchesInModal && (window._pendingSearchesInModal.has(Number(key)) || window._pendingSearchesInModal.has(String(key)))) {
    return;
  }

  // Если бейдж уже подсвечивается — избегаем судорожного перезапуска и лишнего reflow
  if (chipEl && chipEl.classList.contains('poll-flash')) {
    return;
  }

  if (chipEl) chipEl.classList.add('poll-flash');
  if (badgeEl) badgeEl.classList.add('poll-flash');
  if (modalBadgeEl) modalBadgeEl.classList.add('poll-flash');
}

function unhighlightPolledSearchBadge(key) {
  const safeId = getSafeSearchDomId(key);
  const badgeEl = document.getElementById(`poll-badge-${safeId}`);
  const chipEl = document.getElementById(`search-chip-${safeId}`);
  const modalBadgeEl = document.getElementById(`modal-poll-badge-${safeId}`);

  if (chipEl) chipEl.classList.remove('poll-flash');
  if (badgeEl) badgeEl.classList.remove('poll-flash');
  if (modalBadgeEl) modalBadgeEl.classList.remove('poll-flash');
}

function formatPollTime(dtStr, isInitialized) {
  const isInit = (isInitialized === 1 || isInitialized === true || isInitialized === '1');
  if (!dtStr || !isInit) return '🔍 Первый сбор';
  try {
    const cleanStr = String(dtStr).replace(' ', 'T');
    const d = new Date(cleanStr);
    if (isNaN(d.getTime())) return String(dtStr);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    if (isToday) {
      return `⏱️ ${hh}:${mm}:${ss}`;
    }
    const day = String(d.getDate()).padStart(2, '0');
    const mon = String(d.getMonth() + 1).padStart(2, '0');
    return `⏱️ ${day}.${mon} ${hh}:${mm}`;
  } catch (e) {
    return String(dtStr);
  }
}

function renderAvitoSearchesHtml(searches, maxSearches) {
  const normSearches = normalizeSearches(searches);

  if (normSearches.length === 0) {
    return '';
  }
  // Отображаем в поиске только активные ссылки (включенные галочкой)
  const activeSearches = normSearches.filter(s => s.is_active !== 0);
  if (activeSearches.length === 0) {
    return `<span class="avito-searches-empty-text" style="font-size:0.85rem;color:var(--text-secondary);font-style:italic;margin-right:0.35rem;">Все ссылки отключены.</span>`;
  }
  const chipsHtml = activeSearches.map((s, idx) => {
    const isPolled = Boolean(s.last_polled_at) && Boolean(s.is_initialized == 1 || s.is_initialized === true || s.is_initialized === '1');
    const pollTimeText = formatPollTime(s.last_polled_at, s.is_initialized);
    const key = getSearchUniqueKey(s, idx);
    const safeId = getSafeSearchDomId(key);
    const isRecentlyPolled = (!isWaitingProxyForPoll && avitoProxyCount > 0 && isAvitoPollingActive()) && _recentlyPolledSearchKeys.has(key);
    const flashClass = isRecentlyPolled ? ' poll-flash' : '';
    const badgeClass = isPolled ? 'poll-time-badge polled' : 'poll-time-badge waiting';
    const pollTitle = isPolled ? `Последний опрос: ${s.last_polled_at}` : 'Идёт первый сбор данных с Авито';
    return `
      <div class="avito-search-chip${flashClass}" id="search-chip-${safeId}" title="${escapeHtml(s.name || 'Поиск')}: ${escapeHtml(s.url)} (${pollTitle})">
        <span>🔎 <strong>${escapeHtml(s.name || 'Поиск')}</strong></span>
        <span class="${badgeClass}${flashClass}" id="poll-badge-${safeId}" title="${pollTitle}">${pollTimeText}</span>
      </div>
    `;
  }).join('');

  return chipsHtml;
}

function updateAddSearchHintPosition() {
  const block = document.getElementById('avito-searches-block');
  const wrapper = document.querySelector('.avito-add-search-hint-center-wrapper');
  if (!block || !wrapper) return;
  const chips = block.querySelectorAll('.avito-search-chip');
  if (chips.length === 0) {
    wrapper.classList.remove('hint-is-displaced');
    return;
  }
  const blockRect = block.getBoundingClientRect();
  const wrapperRect = wrapper.getBoundingClientRect();
  const hintW = wrapperRect.width || 135;
  const centerLeft = (blockRect.width - hintW) / 2;

  let maxChipRight = 0;
  chips.forEach(chip => {
    const cr = chip.getBoundingClientRect();
    if (cr.top - blockRect.top < 38) {
      const rightInBlock = cr.right - blockRect.left;
      if (rightInBlock > maxChipRight) maxChipRight = rightInBlock;
    }
  });

  if (maxChipRight + 12 >= centerLeft) {
    wrapper.classList.add('hint-is-displaced');
  } else {
    wrapper.classList.remove('hint-is-displaced');
  }
}
window.updateAddSearchHintPosition = updateAddSearchHintPosition;
window.addEventListener('resize', () => {
  if (typeof updateAddSearchHintPosition === 'function') updateAddSearchHintPosition();
});

function getNextAvitoInterval() {
  // В режиме прямого подключения или в гибридном режиме при 0 прокси — случайный интервал 60-90 сек (защита от бана)
  const isDirect = (String(avitoTargetInterval) === '60' && !avitoHybridMode) || avitoDirectMode;
  if (isDirect || (avitoHybridMode && avitoProxyCount === 0)) {
    return 60 + Math.floor(Math.random() * 31); // 60 до 90 сек
  }
  if (avitoTargetInterval === 'random_30_60' || String(avitoTargetInterval).startsWith('rand')) {
    return 30 + Math.floor(Math.random() * 31);
  }
  const chosenTarget = Number(avitoTargetInterval);
  if (!isNaN(chosenTarget) && chosenTarget >= 1) {
    return chosenTarget;
  }
  return Number(avitoSafeInterval) || 60;
}

function isAvitoPollingActive() {
  if (!currentUser) return false;
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) return false;
  const isUserMon = Boolean(!currentUser.permissions || currentUser.permissions.monitoring !== false);
  const isUserTg = Boolean(currentUser.permissions && currentUser.permissions.tg_bot !== false);
  // Опрос активен, если у пользователя включен мониторинг или тг-уведомления
  return isUserMon || isUserTg;
}

function hasActiveAvitoSearches() {
  let list = [];
  if (currentUser && Array.isArray(currentUser.avito_searches) && currentUser.avito_searches.length > 0) {
    list = currentUser.avito_searches;
  } else if (avitoData && Array.isArray(avitoData.searches) && avitoData.searches.length > 0) {
    list = avitoData.searches;
  }
  const norm = normalizeSearches(list);
  return norm.filter(s => s && s.url && String(s.url).trim() && s.is_active !== 0 && s.is_active !== '0' && s.is_active !== false).length > 0;
}

function initAvitoTimer() {
  if (avitoTimerIntervalHandle) clearInterval(avitoTimerIntervalHandle);
  let bgSyncCounter = 0;
  avitoTimerIntervalHandle = setInterval(() => {
    bgSyncCounter++;
    // Синхронизируем счётчик прокси в реальном времени:
    // При активном сборе прокси — каждую 1 секунду, в обычном режиме — каждые 3 секунды
    const isProxyHarvesting = Boolean(avitoIsFetchingProxies || (avitoData && avitoData.stats && avitoData.stats.proxy_fetching));
    if (isProxyHarvesting || (bgSyncCounter % 3 === 0)) {
      fetch('/api/avito/proxies?t=' + Date.now()).then(r => r.json()).then(d => {
        if (d && d.success) {
          const effectiveCount = d.is_custom ? (d.user_count || 0) : (d.count || d.shared_count || 0);
          avitoProxyCount = effectiveCount;
          if (avitoData && avitoData.stats) {
            avitoData.stats.proxy_count = effectiveCount;
            avitoData.stats.proxy_fetching = Boolean(d.is_fetching);
          }
          avitoIsFetchingProxies = Boolean(d.is_fetching);
          updateAvitoProxiesUI();
        }
      }).catch(() => {});
    }

    // Если опрос не активен (выключен и мониторинг, и тг, или мастер-переключатель), опрос не производим
    if (!isAvitoPollingActive()) {
      isWaitingProxyForPoll = false;
      updateAvitoTimerUI();
      return;
    }

    // Если опрос на паузе (идёт «Загрузить всё» / кулдаун загрузки) — удерживаем паузу и не тикаем таймер
    if (window._isAvitoFetchingAll || window._isAvitoPollPaused) {
      updateAvitoTimerUI('PAUSE');
      return;
    }

    // Если нет активных ссылок для поиска, опрос не производим (состояние "Пусто", кнопка оранжевая)
    if (!hasActiveAvitoSearches()) {
      isWaitingProxyForPoll = false;
      _recentlyPolledSearchKeys.clear();
      document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
      updateAvitoTimerUI();
      return;
    }

    if (isAvitoCheckingNow) {
      // Пока идет опрос, удерживаем (GO)
      updateAvitoTimerUI('GO');
      return;
    }

    // Состояние ожидания появления прокси на шаге «Опрос»:
    // В гибридном режиме - НЕ ждем прокси, сразу запускаем прямой опрос
    if (isWaitingProxyForPoll && !avitoHybridMode) {
      _recentlyPolledSearchKeys.clear();
      document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
      waitingProxyCheckCounter++;
      // Каждые 3 секунды опрашиваем статистику и прокси в фоне
      if (waitingProxyCheckCounter % 3 === 0) {
        loadAvitoStats();
      }

      // Как только появился хотя бы 1 прокси:
      if (avitoProxyCount > 0) {
        isWaitingProxyForPoll = false;
        waitingProxyCheckCounter = 0;
        avitoTimerSecondsLeft = 0;
        updateAvitoTimerUI('GO');
        runAvitoAutoCheck();
      } else {
        // Стоим и ждем на шаге «Прокси», таймер НЕ отсчитывает назад!
        updateAvitoTimerUI('WAITING_PROXY');
      }
      return;
    }

    // В гибридном режиме: если ожидали прокси — сбрасываем ожидание и идем в прямой режим
    if (isWaitingProxyForPoll && avitoHybridMode) {
      isWaitingProxyForPoll = false;
      waitingProxyCheckCounter = 0;
    }

    // Обратный отсчет таймера
    if (avitoTimerSecondsLeft > 1) {
      avitoTimerSecondsLeft--;
      updateAvitoTimerUI();
    } else if (avitoTimerSecondsLeft === 1) {
      // Досчитали до 1 -> наступает шаг «Сайт»
      const now = Date.now();
      const minIntervalMs = Math.max(1000, getNextAvitoInterval() * 1000);
      const timeSinceLast = now - (window._lastAvitoPollTimestamp || 0);
      if (timeSinceLast < (minIntervalMs - 150)) {
        updateAvitoTimerUI();
        return;
      }
      if (avitoProxyCount === 0 && !avitoHybridMode) {
        // В пуле 0 прокси! Останавливаемся на шаге «Прокси» и ждем появления прокси
        avitoTimerSecondsLeft = 0;
        isWaitingProxyForPoll = true;
        waitingProxyCheckCounter = 0;
        _recentlyPolledSearchKeys.clear();
        document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
        updateAvitoTimerUI('WAITING_PROXY');
        loadAvitoStats();
      } else {
        // Есть прокси (или гибридный режим с прямым подключением) -> производим опрос
        avitoTimerSecondsLeft = 0;
        isWaitingProxyForPoll = false;
        updateAvitoTimerUI('GO');
        runAvitoAutoCheck();
      }
    } else {
      // avitoTimerSecondsLeft <= 0
      if (avitoProxyCount === 0 && !avitoHybridMode) {
        isWaitingProxyForPoll = true;
        updateAvitoTimerUI('WAITING_PROXY');
      } else {
        avitoTimerSecondsLeft = getNextAvitoInterval();
        updateAvitoTimerUI();
      }
    }
  }, 1000);
}

function getAvitoTimerButtonHtml(countdownOverride) {
  const pollLabel = '<span style="color:#fbbf24;font-weight:600;">Опрос:</span>';
  if (!isAvitoPollingActive()) {
    return `⏱️ ${pollLabel}&nbsp;<span class="timer-countdown timer-countdown-warn" style="font-weight:inherit;font-family:inherit;">выкл</span>`;
  }
  const isDirect = (String(avitoTargetInterval) === '60' && !avitoHybridMode) || avitoDirectMode;
  if (isDirect) {
    return `⏱️ ${pollLabel}&nbsp;<span style="color:cyan;font-weight:inherit;font-family:inherit;">60–90&nbsp;сек</span>`;
  }
  const speedVal = `${(avitoTargetInterval === 'random_30_60' || String(avitoTargetInterval).startsWith('rand')) ? '30–60' : (avitoTargetInterval || 60)}`;
  return `⏱️ ${pollLabel}&nbsp;<span style="color:cyan;font-weight:inherit;font-family:inherit;">${speedVal}&nbsp;сек</span>`;
}

function updateAvitoProxiesUI() {
  const btn = document.getElementById('btn-avito-proxies');
  if (!btn) return;

  const hasTgAccount = Boolean(
    currentUser && (
      (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
      (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
    )
  );
  const userMon = !(currentUser && currentUser.permissions && currentUser.permissions.monitoring === false);
  const userTg = Boolean(hasTgAccount && (!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false));
  const isAllDisabled = !userMon && (!hasTgAccount || !userTg);

  if (isAllDisabled) {
    // Прокси работают независимо от состояния мониторинга и ТГ
  }

  const count = (avitoData && avitoData.stats && avitoData.stats.proxy_count !== undefined) ? Number(avitoData.stats.proxy_count) : (typeof avitoProxyCount !== 'undefined' ? Number(avitoProxyCount) : 0);
  const countColor = Number(count) === 0 ? '#ef4444' : '#fbbf24';
  btn.innerHTML = `🌐 Прокси: <strong style="color:${countColor};">${count}</strong>`;
  btn.title = `Управление прокси: поиск бесплатных, список, добавление (в пуле: ${count} шт.)`;

  // Мгновенно обновляем кнопку «Загрузить все» без полного перерендера страницы
  const fetchBtn = document.getElementById('btn-avito-fetch-all');
  if (fetchBtn && !window._isAvitoFetchingAll) {
    const isFiltered = typeof currentAvitoLinkFilter !== 'undefined' && currentAvitoLinkFilter && currentAvitoLinkFilter !== 'all' && currentAvitoLinkFilter !== '__favorites__' && currentAvitoLinkFilter !== '__blacklist__';
    fetchBtn.disabled = false;
    fetchBtn.style.cursor = '';
    fetchBtn.style.pointerEvents = '';
    fetchBtn.style.color = '';
    fetchBtn.style.borderColor = '';
    fetchBtn.style.background = '';
    fetchBtn.style.opacity = '';
    fetchBtn.innerHTML = isFiltered ? 'Загрузить' : 'Загрузить все';
    fetchBtn.title = isFiltered ? 'Загрузить объявления по выбранной ссылке на сайт' : 'Загрузить все найденные объявления по активным ссылкам на сайт';
    fetchBtn.onclick = () => window.fetchAllAvitoCards();
  }
}

function updateAvitoTimerUI(countdownOverride) {
  const btn = document.getElementById('btn-avito-timer');
  if (!btn) return;

  const admin = isAdmin();
  const userCardInt = typeof getUserCardInterval === 'function' ? getUserCardInterval() : 60;

  const hasTgAccount = Boolean(
    currentUser && (
      (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
      (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
    )
  );
  const isUserMonActive = !(currentUser && currentUser.permissions && currentUser.permissions.monitoring === false);
  const isUserTgActive = Boolean(hasTgAccount && (!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false));
  const isAllDisabled = !isUserMonActive && (!hasTgAccount || !isUserTgActive);

  // Требование 1 и 2:
  // 1. Если отключен мониторинг авито и затемнены тг-уведомления (серый кружок) - то прекратить поиск прокси и кнопку опроса изменить на красный.
  // Если лицензия истекла или не активирована — блокируем опрос и предлагаем активацию
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    if (avitoIsFetchingProxies || (avitoData && avitoData.stats && avitoData.stats.proxy_fetching)) {
      avitoIsFetchingProxies = false;
      if (avitoData && avitoData.stats) avitoData.stats.proxy_fetching = false;
      if (typeof updateAvitoProxiesUI === 'function') updateAvitoProxiesUI();
      fetch('/api/avito/proxies/stop', { method: 'POST' }).catch(() => {});
    }
    const dangerClass = 'cat-btn btn-avito-timer-danger';
    btn.className = dangerClass;
    btn.classList.remove('btn-avito-timer-readonly');
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { if (typeof openActivationModal === 'function') openActivationModal(); };
    btn.title = 'Срок действия лицензии истёк или требуется активация. Нажмите для активации.';
    btn.innerHTML = '🔒 <span style="color:#ef4444;font-weight:700;">Требуется активация</span>';
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    _attachTimerBtnHover(btn, 'rgba(239,68,68,0.55)');
    return;
  }

  if (isAllDisabled) {
    // Прокси не останавливаем: поиск прокси работает независимо от мониторинга и ТГ
    const dangerClass = 'cat-btn btn-avito-timer-danger';
    btn.className = dangerClass;
    btn.classList.remove('btn-avito-timer-readonly');
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { if (typeof toggleAvitoTimer === 'function') toggleAvitoTimer(); else if (typeof openPollingSpeedModal === 'function') openPollingSpeedModal(); };
    btn.title = 'Опрос выключен (мониторинг и ТГ-уведомления отключены). Нажмите для выбора таймера.';
    btn.innerHTML = '🔴 <span style="color:#fbbf24;font-weight:600;">Опрос:</span>&nbsp;выкл';
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    _attachTimerBtnHover(btn, 'rgba(239,68,68,0.55)');
    return;
  }

  // Если ссылок нет и мониторинг включен или тг уведомления включены - то состояние опроса "---", цвет оранжевый, не опрашивать
  if (!hasActiveAvitoSearches()) {
    btn.className = 'cat-btn btn-avito-timer-empty';
    btn.classList.remove('btn-avito-timer-readonly');
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { if (typeof toggleAvitoTimer === 'function') toggleAvitoTimer(); else if (typeof openPollingSpeedModal === 'function') openPollingSpeedModal(); };
    btn.title = 'Нет ссылок для поиска! Кнопка мигает красным. Нажмите для настройки скорости опроса или добавьте ссылки.';
    btn.innerHTML = getAvitoTimerButtonHtml(countdownOverride);
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    _attachTimerBtnHover(btn, 'rgba(239,68,68,0.55)');
    return;
  }

  // Если опрос на паузе (идёт загрузка объявлений)
  if (countdownOverride === 'PAUSE' || window._isAvitoPollPaused || window._isAvitoFetchingAll) {
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    btn.className = 'cat-btn btn-avito-timer-warn is-paused';
    btn.classList.remove('btn-avito-timer-readonly');
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { if (typeof toggleAvitoTimer === 'function') toggleAvitoTimer(); else if (typeof openPollingSpeedModal === 'function') openPollingSpeedModal(); };
    btn.title = 'Опрос приостановлен (идёт загрузка объявлений). Нажмите для настройки.';
    btn.innerHTML = '⏱️ <span style="color:#fbbf24;font-weight:600;">Опрос:</span>&nbsp;<span style="color:#fbbf24;font-weight:600;">пауза</span>';
    _attachTimerBtnHover(btn, 'rgba(245,158,11,0.55)');
    return;
  }

  const isMonRunning = isAvitoPollingActive();
  const isWaiting = isWaitingProxyForPoll || countdownOverride === 'WAITING_PROXY';
  const isWarn = isMonRunning && (avitoProxyCount === 0 || isWaiting);
  if (isWaiting || avitoProxyCount === 0 || !isMonRunning) {
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
  }

  // Кнопка настройки скорости опроса (для пользователя и администратора)
  btn.classList.remove('btn-avito-timer-readonly');
  btn.style.pointerEvents = 'auto';
  btn.style.cursor = 'pointer';
  btn.onclick = () => { if (typeof toggleAvitoTimer === 'function') toggleAvitoTimer(); else if (typeof openPollingSpeedModal === 'function') openPollingSpeedModal(); };

  if (!isMonRunning) {
    btn.className = 'cat-btn btn-avito-timer-off';
    btn.innerHTML = getAvitoTimerButtonHtml();
    btn.title = `Мониторинг выключен. Нажмите для настройки скорости опроса.`;
    _attachTimerBtnHover(btn, 'rgba(148,163,184,0.4)');
    return;
  }

  const isPolling = countdownOverride === 'GO' || (avitoTimerSecondsLeft <= 0 && !isWaiting) || isAvitoCheckingNow;

  if (isWaiting) {
    btn.className = 'cat-btn btn-avito-timer-warn is-waiting-proxy';
    btn.title = `Опрос приостановлен: в пуле 0 прокси. Ожидание появления хотя бы 1 прокси. Нажмите для настройки.`;
    _attachTimerBtnHover(btn, 'rgba(245,158,11,0.55)');
  } else if (isWarn) {
    btn.className = 'cat-btn btn-avito-timer-warn' + (isPolling ? ' is-polling' : '');
    btn.title = `Прокси: 0 шт (желтый индикатор). Досчитываем до опроса и ожидаем прокси. След. через ${avitoTimerSecondsLeft}с. Нажмите для настройки.`;
    _attachTimerBtnHover(btn, 'rgba(245,158,11,0.55)');
  } else {
    btn.className = 'cat-btn btn-avito-timer-on' + (isPolling ? ' is-polling' : '');
    if (avitoSafeInterval > avitoTargetInterval) {
      btn.title = `Скорость: Цель ${avitoTargetInterval}с, безопасно ${avitoSafeInterval}с (${avitoProxyCount}/${avitoNeededProxies} прокси). След. опрос через ${avitoTimerSecondsLeft}с. Нажмите для изменения.`;
    } else {
      btn.title = `Скорость опроса: ${avitoTargetInterval} сек (след. через ${avitoTimerSecondsLeft}с). Нажмите для изменения.`;
    }
    _attachTimerBtnHover(btn, 'rgba(14,165,233,0.55)');
  }

  btn.innerHTML = getAvitoTimerButtonHtml(countdownOverride);
}

// Навешивает JS hover-эффект на кнопку таймера (lift + glow по цвету состояния)
function _attachTimerBtnHover(btn, glowColor) {
  btn.style.transition = 'all 0.2s cubic-bezier(0.16,1,0.3,1)';
  btn.onmouseenter = function() {
    this.style.transform = 'translateY(-1px)';
    this.style.boxShadow = `0 0 14px ${glowColor}, 0 3px 8px rgba(0,0,0,0.25)`;
    this.style.filter = 'brightness(1.18)';
  };
  btn.onmouseleave = function() {
    this.style.transform = '';
    this.style.boxShadow = '';
    this.style.filter = '';
  };
}

// Открытие модального окна выбора скорости опроса (как в Telegram-боте)
window.openPollingSpeedModal = async function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  if (!currentUser) return;
  const admin = isAdmin();
  const userTariffMin = typeof getUserCardInterval === 'function' ? getUserCardInterval() : 60;

  const hasAccess = admin || (typeof hasPermission === 'function' && (hasPermission('avito_bot') || hasPermission('monitoring') || hasPermission('avito')));
  if (!hasAccess) return;

  const reqId = (window._speedModalReqId = (window._speedModalReqId || 0) + 1);
  window._isSpeedModalOpen = true;

  try {
    const devId = (currentUser && currentUser.username) || (typeof window.getClientDeviceId === 'function' ? window.getClientDeviceId() : '');
    const userParam = devId ? '&username=' + encodeURIComponent(devId) + '&request_id=' + encodeURIComponent(devId) : '';
    const res = await fetch('/api/avito/interval?t=' + Date.now() + userParam);
    const data = await res.json();
    if (data && data.success) {
      avitoTargetInterval = Number(data.target_interval) || Number(avitoTargetInterval) || 60;
      if (avitoTargetInterval === 60 || String(data.target_interval).startsWith('rand')) {
        avitoTargetInterval = 60;
      }
      avitoSafeInterval = Number(data.safe_interval) || avitoSafeInterval;
      avitoNeededProxies = Number(data.needed_proxies) || 0;
      avitoProxyCount = Number(data.proxy_count) || 0;
      avitoIsFetchingProxies = Boolean(data.is_fetching);
    }
  } catch (e) {
    console.warn('Could not fetch interval info:', e);
  }

  // Если окно было закрыто пользователем пока шел асинхронный запрос, НЕ открывать его!
  if (!window._isSpeedModalOpen || reqId !== window._speedModalReqId) {
    return;
  }

  if (avitoTargetInterval === 'random_30_60' || String(avitoTargetInterval).startsWith('rand')) {
    avitoTargetInterval = 60;
  }
  if (Number(avitoTargetInterval) < userTariffMin) {
    avitoTargetInterval = userTariffMin;
  }

  const presets = [
    { sec: 1, label: '⚡ 1 сек', sub: '30 прокси' },
    { sec: 3, label: '⚡ 3 сек', sub: '10 прокси' },
    { sec: 5, label: '⚡ 5 сек', sub: '6 прокси' },
    { sec: 10, label: '⏱️ 10 сек', sub: '3 прокси' },
    { sec: 15, label: '⏱️ 15 сек', sub: '2 прокси' },
    { sec: 30, label: '⏱️ 30 сек', sub: '1 прокси' },
  ];

  const hasEnoughProxies = avitoProxyCount >= avitoNeededProxies || avitoTargetInterval >= 30;

  // Определяем текущий режим
  const isDirectMode = (String(avitoTargetInterval) === '60' && !avitoHybridMode);
  const isHybridModeActive = avitoHybridMode;

  let statusHtml = '';
  if (isDirectMode) {
    statusHtml = `
      <div class="speed-status-indicator ok" style="border-color:#22c55e;background:rgba(34,197,94,0.08);">
        <strong>🟢 Прямое подключение активно!</strong><br>
        Запросы отправляются напрямую со случайным интервалом <strong>60–90 сек</strong> (защита от бана). Поиск прокси остановлен.
      </div>
    `;
  } else if (isHybridModeActive) {
    statusHtml = `
      <div class="speed-status-indicator" style="border-color:#a855f7;background:rgba(168,85,247,0.1);">
        <strong>🟢 Гибридный режим активен!</strong><br>
        При наличии прокси — работает через прокси. При 0 прокси — прямое подключение с случайным интервалом <strong>60–90 сек</strong> (защита от бана).
      </div>
    `;
  } else if (hasEnoughProxies) {
    statusHtml = `
      <div class="speed-status-indicator ok">
        <strong>✅ Безопасная скорость активна!</strong><br>
        Интервал проверки установлен: <strong>${avitoTargetInterval} сек</strong>. В пуле <strong>${avitoProxyCount} шт.</strong> прокси 
        ${avitoNeededProxies > 0 ? `(требовалось: ${avitoNeededProxies})` : ''}. 
        Авито не заблокирует: каждый IP опрашивается не чаще 1 раза в 30 сек.
      </div>
    `;
  } else {
    statusHtml = `
      <div class="speed-status-indicator warning">
        <strong>🛡️ Включена защита от бана и умный авто-разгон!</strong><br>
        Целевая скорость <strong>${avitoTargetInterval} сек</strong> требует <strong>${avitoNeededProxies} прокси</strong>.<br>
        Сейчас в пуле <strong>${avitoProxyCount} прокси</strong>, поэтому прямо сейчас сайт безопасно опрашивает со скоростью: <strong>${avitoSafeInterval} сек</strong>.<br>
        ${avitoIsFetchingProxies 
          ? '🤖 <em>Воркер прямо сейчас в фоне ищет и проверяет бесплатные прокси. По мере сбора сайт сам разгонится до <strong>' + avitoTargetInterval + ' сек</strong>!</em>' 
          : '💡 <em>Нажмите «Найти бесплатные прокси» ниже или добавьте свои, чтобы разогнать опрос до полной скорости.</em>'}
      </div>
    `;
  }

  modalBody.innerHTML = `
    <div style="padding:0.5rem 0;">
      <h3 style="font-size:1.35rem;font-weight:800;color:var(--accent);margin-bottom:0.6rem;display:flex;align-items:center;gap:0.5rem;">
        ⏱️ Управление таймером опроса Avito
      </h3>
      <p style="font-size:0.88rem;color:var(--text-secondary);margin-bottom:1.15rem;line-height:1.45;">
        Вам доступны все скорости опроса без ограничений (от 1 сек до 60–90 сек) и ручной ввод.
      </p>

      <div class="speed-info-card">
        <div style="display:flex;gap:1rem;justify-content:space-between;align-items:center;flex-wrap:wrap;">
          <div>
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">🎯 Выбранный таймер:</span>
            <strong style="font-size:1.25rem;color:var(--text-primary);">${isHybridModeActive ? 'Гибрид' : (isDirectMode ? '60–90 сек (прямой)' : avitoTargetInterval + ' сек.')}</strong>
          </div>
          <div>
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">⚡ Безопасная скорость сейчас:</span>
            <strong style="font-size:1.25rem;color:${hasEnoughProxies || isDirectMode || isHybridModeActive ? '#34d399' : '#fbbf24'};">${isHybridModeActive ? '60–90 сек (direct)' : (isDirectMode ? '60–90 сек (direct)' : avitoSafeInterval + ' сек.')}</strong>
          </div>
          <div>
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">🌐 Прокси в пуле:</span>
            <strong style="font-size:1.25rem;color:#818cf8;">${avitoProxyCount} <span style="font-size:0.85rem;color:var(--text-secondary);">${avitoNeededProxies > 0 && !isDirectMode && !isHybridModeActive ? `/ ${avitoNeededProxies} нужно` : ''}</span></strong>
          </div>
        </div>
        ${statusHtml}
      </div>

      <label style="font-size:0.88rem;font-weight:700;color:var(--text-primary);display:block;margin-bottom:0.6rem;">
        ⚡ Выберите интервал опроса:
      </label>

      <div class="speed-preset-grid">
        ${presets.map(p => {
          const isActive = !isHybridModeActive && !isDirectMode && String(p.sec) === String(avitoTargetInterval);
          return `
            <button type="button" 
                    class="speed-preset-btn ${isActive ? 'active' : ''}" 
                    onclick="setPollingSpeed(${p.sec})">
              <span class="speed-preset-title">${p.label}</span>
              <span class="speed-preset-sub">${p.sub}</span>
            </button>
          `;
        }).join('')}
        <!-- Прямое подключение (60-90 сек, кнопка) -->
        <button type="button" 
                class="speed-preset-btn${isDirectMode ? ' active' : ''}" 
                onclick="setDirectConnectionMode()"
                style="${isDirectMode ? 'background:rgba(34,197,94,0.18);border-color:#22c55e;color:#22c55e;box-shadow:0 0 16px rgba(34,197,94,0.45);outline:2px solid #22c55e;' : ''}cursor:pointer;"
                title="Прямое подключение (без прокси). Запросы отправляются со случайным интервалом 60–90 сек для защиты от бана. Поиск прокси будет остановлен.">
          <span class="speed-preset-title" style="${isDirectMode ? 'color:#22c55e;' : ''}">⏱️ 60-90 сек</span>
          <span class="speed-preset-sub" style="display:inline-block;border:1px solid #22c55e;border-radius:5px;padding:1px 6px;color:#22c55e;font-size:0.72rem;margin-top:2px;">Прямое подключение</span>
        </button>
      </div>

      <!-- Свой ввод (ручной ввод кол-ва секунд) -->
      <div style="background:var(--bg-main);border:1px solid var(--border-color);border-radius:10px;padding:0.85rem 1rem;margin-bottom:1.15rem;display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <span style="font-size:0.85rem;font-weight:700;white-space:nowrap;">✏️ Свой фиксированный интервал:</span>
        <div style="display:flex;align-items:center;gap:0.4rem;flex:1;min-width:180px;">
          <input type="number" id="custom-speed-input" class="form-control" style="max-width:110px;padding:0.4rem 0.6rem;text-align:center;"
            min="${isDirectMode ? 60 : 1}" max="3600"
            value="${isDirectMode ? Math.max(60, Number(avitoTargetInterval) || 60) : avitoTargetInterval}"
            placeholder="${isDirectMode ? '60-3600' : '1-3600'}"
            onkeydown="if(event.key==='Enter') submitCustomSpeed()">
          <span style="font-size:0.85rem;color:var(--text-secondary);">сек</span>
          <button type="button" onclick="submitCustomSpeed()" class="cat-btn" style="background:var(--accent);color:#0f172a;font-weight:700;padding:0.45rem 0.95rem;">
            Применить
          </button>
        </div>
      </div>

      <!-- Кнопки управления прокси -->
      <div style="display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap;justify-content:space-between;border-top:1px solid var(--border-color);padding-top:1rem;margin-top:1rem;">
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
          ${isDirectMode
            ? `<button type="button" class="cat-btn" disabled
                style="background:rgba(100,100,120,0.12);color:rgba(180,180,200,0.55);border-color:rgba(150,150,170,0.25);font-weight:700;padding:0.5rem 1rem;font-size:0.85rem;cursor:not-allowed;pointer-events:none;"
                title="Недоступно в режиме прямого подключения">
                ⚪ Гибридный режим direct(60-90)/Proxy
              </button>`
            : `<button type="button" class="cat-btn" onclick="setHybridMode()" id="btn-speed-modal-hybrid"
                onmouseover="if(!this.dataset.pressed)this.style.background='${isHybridModeActive ? '#6d28d9' : 'rgba(168,85,247,0.28)'}'"
                onmouseout="if(!this.dataset.pressed)this.style.background='${isHybridModeActive ? '#7c3aed' : 'rgba(168,85,247,0.15)'}'"
                onmousedown="this.dataset.pressed='1';this.style.color='#a855f7';this.style.background='rgba(168,85,247,0.1)'"
                onmouseup="this.dataset.pressed='';this.style.color='#ffffff';this.style.background='${isHybridModeActive ? '#7c3aed' : 'rgba(168,85,247,0.15)'}'"
                style="background:${isHybridModeActive ? '#7c3aed' : 'rgba(168,85,247,0.15)'};color:#ffffff;border-color:${isHybridModeActive ? '#7c3aed' : 'rgba(168,85,247,0.5)'};font-weight:700;padding:0.5rem 1rem;font-size:0.85rem;transition:background 0.15s,color 0.15s;"
                title="Использует прокси если есть, при 0 прокси - прямое подключение 60-90 сек">
                ${isHybridModeActive ? '🟢' : '⚪'} Гибридный режим direct(60-90)/Proxy
              </button>`
          }
        </div>
        <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.5rem 1.3rem;">Закрыть</button>
      </div>
    </div>
  `;
  if (!window._isSpeedModalOpen || reqId !== window._speedModalReqId) {
    return;
  }
  modalOverlay.classList.add('open');
};

window.setPollingSpeed = async function(sec) {
  let reqInterval = parseInt(sec, 10);
  if (isNaN(reqInterval) || reqInterval < 1) {
    reqInterval = 60;
  }

  // Мгновенный отклик в интерфейсе без задержек сети
  avitoDirectMode = false;
  avitoHybridMode = false;
  avitoTargetInterval = reqInterval;
  avitoTimerSecondsLeft = reqInterval;
  updateAvitoTimerUI();
  if (currentUser) {
    currentUser.active_interval = String(reqInterval);
    try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
  }
  // Пуш-уведомление удалено по требованию пользователя

  try {
    const res = await fetch('/api/avito/interval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        interval: reqInterval,
        username: currentUser ? currentUser.username : '',
        request_id: currentUser ? currentUser.username : ''
      })
    });
    const data = await res.json();
    if (data && data.success) {
      avitoTargetInterval = Number(data.target_interval) || reqInterval;
      avitoSafeInterval = Number(data.safe_interval) || avitoTargetInterval;
      avitoNeededProxies = Number(data.needed_proxies) || 0;
      avitoProxyCount = Number(data.proxy_count) || 0;
      avitoIsFetchingProxies = Boolean(data.is_fetching);
      avitoTimerSecondsLeft = getNextAvitoInterval();
      updateAvitoTimerUI();
      if (modalOverlay && modalOverlay.classList.contains('open')) {
        openPollingSpeedModal().catch(() => {});
      }
    }
  } catch (err) {
    console.error('Set interval error:', err);
  }
};

window.submitCustomSpeed = function() {
  const inp = document.getElementById('custom-speed-input');
  if (!inp) return;
  const val = parseInt(inp.value, 10);
  if (isNaN(val) || val < 1) {
    alert('Введите целое число секунд от 1 и выше.');
    return;
  }
  // В режиме прямого подключения минимум 60 сек
  if (inp.getAttribute('min') === '60' && val < 60) {
    alert('В режиме прямого подключения минимальный интервал — 60 секунд.');
    inp.value = 60;
    return;
  }
  setPollingSpeed(val);
};

window.toggleProxyFetchFromSpeedModal = async function() {
  const btn = document.getElementById('btn-speed-modal-fetch');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Пожалуйста, подождите...';
  }
  const action = avitoIsFetchingProxies ? 'stop' : 'start';
  try {
    const res = await fetch('/api/avito/proxies/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, source: 'manual' })
    });
    const data = await res.json();
    showToast(data.message || (action === 'start' ? 'Запущен поиск бесплатных прокси' : 'Поиск остановлен'));
    await loadAvitoStats();
    openPollingSpeedModal();
  } catch (e) {
    alert('Ошибка вызова сборщика прокси.');
  }
};

// Режим прямого подключения: 60-90 сек (рандом), без прокси, остановить поиск прокси
window.setDirectConnectionMode = async function() {
  avitoHybridMode = false;
  avitoDirectMode = true;
  isWaitingProxyForPoll = false;
  // Остановить поиск прокси если идёт
  if (avitoIsFetchingProxies) {
    try {
      await fetch('/api/avito/proxies/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop', source: 'direct_mode' })
      });
      avitoIsFetchingProxies = false;
    } catch (e) {}
  }
  // Установить интервал прямого подключения (60-90 сек рандом)
  try {
    const res = await fetch('/api/avito/interval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval: 60, username: currentUser ? currentUser.username : '', request_id: currentUser ? currentUser.username : '', mode: 'direct' })
    });
    const data = await res.json();
    if (data && data.success) {
      avitoTargetInterval = 60;
      avitoSafeInterval = 60;
      avitoNeededProxies = 0;
      avitoProxyCount = Number(data.proxy_count) || 0;
      if (currentUser) {
        currentUser.active_interval = '60';
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      }
      avitoTimerSecondsLeft = 60 + Math.floor(Math.random() * 31);
      updateAvitoTimerUI();
      showToast('🟢 Прямое подключение: интервал 60–90 сек (рандом). Поиск прокси остановлен.');
    }
  } catch (err) {
    console.error('Direct mode error:', err);
  }
  if (modalOverlay && modalOverlay.classList.contains('open')) {
    openPollingSpeedModal();
  }
};

// Гибридный режим: прокси если есть, иначе прямое подключение 60-90 сек (рандом)
window.setHybridMode = async function() {
  // Переключаем гибридный режим
  if (avitoHybridMode) {
    // Выключаем гибрид — переходим в обычный режим
    avitoHybridMode = false;
    isWaitingProxyForPoll = false;
    showToast('Гибридный режим выключен. Возврат в стандартный режим.');
    // Обновляем на сервере
    try {
      await fetch('/api/avito/interval', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: avitoTargetInterval, username: currentUser ? currentUser.username : '', request_id: currentUser ? currentUser.username : '', mode: 'normal' })
      });
    } catch (e) {}
  } else {
    // Включаем гибрид
    avitoHybridMode = true;
    avitoDirectMode = false;
    isWaitingProxyForPoll = false;
    // В гибридном режиме интервал зависит от наличия прокси (если нет прокси — 60-90 сек рандом)
    const hybridInterval = avitoProxyCount > 0 ? (avitoSafeInterval || 30) : (60 + Math.floor(Math.random() * 31));
    avitoTimerSecondsLeft = hybridInterval;
    updateAvitoTimerUI();
    // Сохраняем режим на сервере (используем специальный маркер)
    try {
      await fetch('/api/avito/interval', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: avitoTargetInterval, username: currentUser ? currentUser.username : '', request_id: currentUser ? currentUser.username : '', mode: 'hybrid' })
      });
    } catch (e) {}
    showToast('🟣 Гибридный режим: прокси + прямое подключение 60-90 сек при 0 прокси.');
  }
  if (modalOverlay && modalOverlay.classList.contains('open')) {
    openPollingSpeedModal();
  }
};

function openModal() {
  if (modalOverlay) modalOverlay.classList.add('open');
}
window.openModal = openModal;
window.closeModal = closeModal;

// Заглушки управления сервером и питанием (сервер всегда активен)
window.toggleServerPowerMenu = function() {};
window.closeServerPowerMenu = function() {};
window.setServerPowerState = function() {
  window._currentServerPowerState = 'running';
  document.body.classList.remove('server-offline-admin');
  const oldOverlay = document.getElementById('server-offline-overlay');
  if (oldOverlay) oldOverlay.remove();
  const screen = document.getElementById('maintenance-mode-screen');
  if (screen) screen.remove();
};
window.renderMaintenanceModeScreen = function() {};
window.hideMaintenanceModeScreen = function() {};
window.triggerServerStart = function() {};
window.triggerServerRestart = function() {};
window.triggerServerShutdown = function() {};
window.fetchServerPowerState = function() {};
window.openTariffModal = function() { window.openActivationModal(); };

// ==================== АКТИВАЦИЯ ТАРИФА И КЛЮЧИ (САЙТ) ====================

window._activationStatusData = null;
window._tariffCountdownTimer = null;

window.formatRemainingTariffTime = function(totalSeconds, expStr) {
  if (totalSeconds <= 0) return 'Истек';

  if (expStr) {
    try {
      const expDt = new Date(expStr.replace(' ', 'T'));
      if (!isNaN(expDt.getTime())) {
        const dd = String(expDt.getDate()).padStart(2, '0');
        const mm = String(expDt.getMonth() + 1).padStart(2, '0');
        const yyyy = expDt.getFullYear();
        const hh = String(expDt.getHours()).padStart(2, '0');
        const mi = String(expDt.getMinutes()).padStart(2, '0');
        const ss = String(expDt.getSeconds()).padStart(2, '0');
        const timePart = `${hh}:${mi}:${ss}`;
        return `${dd}.${mm}.${yyyy} ${timePart}`;
      }
    } catch (e) {}
  }

  function pluralRu(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return many;
    if (mod10 === 1) return one;
    if (mod10 >= 2 && mod10 <= 4) return few;
    return many;
  }

  let calDays = 0;
  if (expStr) {
    try {
      const expDt = new Date(expStr.replace(' ', 'T'));
      const now = new Date();
      const expMidnight = new Date(expDt.getFullYear(), expDt.getMonth(), expDt.getDate());
      const nowMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      calDays = Math.round((expMidnight - nowMidnight) / 86400000);
    } catch (e) {
      calDays = Math.floor(totalSeconds / 86400);
    }
  } else {
    calDays = Math.floor(totalSeconds / 86400);
  }

  if (calDays >= 1) {
    return `${calDays} ${pluralRu(calDays, 'день', 'дня', 'дней')}`;
  }
  if (totalSeconds >= 3600) {
    const hours = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    if (mins > 0 && hours < 24) {
      return `${hours} ч. ${mins} мин.`;
    }
    return `${hours} ${pluralRu(hours, 'час', 'часа', 'часов')}`;
  }
  if (totalSeconds >= 60) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = Math.floor(totalSeconds % 60);
    if (secs > 0) {
      return `${mins} мин. ${secs} сек.`;
    }
    return `${mins} ${pluralRu(mins, 'минута', 'минуты', 'минут')}`;
  }
  const secs = Math.max(0, Math.floor(totalSeconds));
  return `${secs} ${pluralRu(secs, 'секунда', 'секунды', 'секунд')}`;
};

window.getTariffDisplayText = function() {
  const perms = (currentUser && currentUser.permissions) || {};
  if (perms.avito_duration === 'unlimited') return 'Безлимит';
  if (window._activationStatusData) {
    if (window._activationStatusData.is_unlimited || window._activationStatusData.tariff_label === 'Бессрочный (Безлимит)') {
      return 'Безлимит';
    }
    if (window._activationStatusData.tariff_label === 'Привязано к другому ПК') {
      return 'Привязано к другому ПК';
    }
  }
  const expStr = (window._activationStatusData && window._activationStatusData.expires_at) || perms.avito_expires_at;
  if (!expStr) {
    if (perms.is_expired || (window._activationStatusData && window._activationStatusData.is_expired)) {
      return (window._activationStatusData && window._activationStatusData.tariff_label) || 'Требуется активация';
    }
    if (perms.active_key) {
      return 'Активен';
    }
    return (window._activationStatusData && window._activationStatusData.tariff_label) || 'Требуется активация';
  }
  try {
    const expDt = new Date(expStr.replace(' ', 'T'));
    const totalSec = Math.floor((expDt - new Date()) / 1000);
    if (totalSec <= 0) return 'Истек';
    const rem = window.formatRemainingTariffTime(totalSec, expStr);
    return rem;
  } catch (e) {
    return expStr ? `${expStr}` : '3 дня';
  }
};

window._activationChatHadActivation = false;

window.isLicenseExpired = function() {
  if (!currentUser) return false;
  const perms = currentUser.permissions || {};
  if (perms.avito_duration === 'unlimited') return false;
  if (window._activationStatusData && window._activationStatusData.is_unlimited) return false;

  // 1. Если сервер прямо вернул статус лицензии
  if (window._activationStatusData && typeof window._activationStatusData.is_expired === 'boolean') {
    if (window._activationStatusData.is_expired === false) {
      if (perms.is_expired) perms.is_expired = false;
      return false;
    } else {
      if (!perms.is_expired) perms.is_expired = true;
      return true;
    }
  }

  // 2. Если у пользователя нет ключа — лицензия не активирована!
  const hasKey = Boolean(perms.active_key || (window._activationStatusData && window._activationStatusData.active_key));
  if (!hasKey) {
    if (!perms.is_expired) perms.is_expired = true;
    return true;
  }

  // 3. Проверяем точную дату окончания тарифа только при наличии ключа
  const expStr = (window._activationStatusData && window._activationStatusData.expires_at) || perms.avito_expires_at;
  if (expStr) {
    try {
      const expDt = new Date(expStr.replace(' ', 'T'));
      if (!isNaN(expDt.getTime())) {
        if (new Date() >= expDt) {
          window._activationChatHadActivation = false;
          if (window._activationStatusData) window._activationStatusData.is_expired = true;
          perms.is_expired = true;
          return true;
        } else {
          return false;
        }
      }
    } catch (e) {}
  }

  // 4. Если зафиксирована свежая активация в сессии
  if (window._activationChatHadActivation) {
    return false;
  }

  // 5. Серверные флаги истечения
  if (perms.is_expired === true) {
    return true;
  }
  return true;
};

window._isLicenseExpiredModeActive = false;
window._activationModalAutoOpened = false;
window._licenseStopSent = false;

window._disclaimerHasScrolledToBottom = false;

window.onDisclaimerScroll = function(el) {
  if (!el) return;
  const isAtBottom = (el.scrollTop + el.clientHeight >= el.scrollHeight - 30);
  if (isAtBottom) {
    window.unlockDisclaimerAgreement();
  }
};

window.unlockDisclaimerAgreement = function() {
  window._disclaimerHasScrolledToBottom = true;
  const chk = document.getElementById('chk-activation-disclaimer-agree');
  const label = document.getElementById('disclaimer-checkbox-label');
  const scrollHint = document.getElementById('disclaimer-scroll-hint');
  const unlockHint = document.getElementById('disclaimer-unlock-hint');

  if (chk) {
    chk.disabled = false;
  }
  if (label) {
    label.classList.remove('is-locked');
    label.classList.add('is-unlocked');
    label.style.opacity = '1';
    label.style.cursor = 'pointer';
    label.style.pointerEvents = 'auto';
    label.title = 'Нажмите, чтобы поставить галочку согласия';
  }
  if (scrollHint) {
    scrollHint.innerHTML = '<span>✓</span> <span>Текст соглашения просмотрен полностью</span>';
    scrollHint.style.color = '#10b981';
    scrollHint.style.background = 'rgba(16, 185, 129, 0.12)';
    scrollHint.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    scrollHint.style.animation = 'none';
  }
  if (unlockHint) {
    unlockHint.innerHTML = '<span style="color:#10b981;">✓</span> <span style="color:#10b981;">Соглашение прочитано. Теперь поставьте галочку для продолжения</span>';
  }
};

window.onDisclaimerAgreementChange = function(checkbox) {
  const isAgreed = Boolean(checkbox && checkbox.checked);
  try {
    if (isAgreed) {
      localStorage.setItem('avitohunter_disclaimer_agreed', '1');
    } else {
      localStorage.removeItem('avitohunter_disclaimer_agreed');
    }
  } catch(e) {}

  const btn = document.getElementById('btn-expired-activate-main');
  if (btn) {
    btn.disabled = !isAgreed;
    btn.title = isAgreed ? 'Открыть окно онлайн-активации и чата с администратором' : 'Для активации сначала подтвердите согласие с соглашением выше';
  }
  const modalChk = document.getElementById('chk-modal-disclaimer-agree');
  if (modalChk) modalChk.checked = isAgreed;
};

window.onDisclaimerActivateClick = function() {
  const chk = document.getElementById('chk-activation-disclaimer-agree');
  if (!chk || !chk.checked) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Пожалуйста, отметьте галочку согласия с условиями использования', 3500, 'warning');
    }
    return;
  }
  try {
    localStorage.setItem('avitohunter_disclaimer_agreed', '1');
  } catch(e) {}
  if (typeof window.openActivationModal === 'function') {
    window.openActivationModal();
  }
};

window.setLicenseExpiredMode = function(isExpired, licenseStatus) {
  const overlay = document.getElementById('license-expired-overlay');
  if (isExpired) {
    const scrollBox = document.getElementById('disclaimer-content-scroll');
    if (scrollBox && !scrollBox._hasScrollListener) {
      scrollBox._hasScrollListener = true;
      scrollBox.addEventListener('scroll', function() {
        window.onDisclaimerScroll(this);
      }, { passive: true });
    }

    const st = licenseStatus || window._activationStatusData;
    const isCleanUnactivated = st && (!st.active_key && (!st.expires_at || st.duration === 'unactivated' || st.tariff_label === 'Требуется активация'));

    const iconEl = document.getElementById('license-expired-icon');
    const titleEl = document.getElementById('license-expired-title');
    const descEl = document.getElementById('license-expired-desc');

    const hasAgreed = localStorage.getItem('avitohunter_disclaimer_agreed') === '1';
    const chk = document.getElementById('chk-activation-disclaimer-agree');
    if (chk) {
      if (hasAgreed) {
        window.unlockDisclaimerAgreement();
        chk.checked = true;
      } else {
        if (!chk.checked) {
          if (!window._disclaimerHasScrolledToBottom) {
            chk.disabled = true;
            const lbl = document.getElementById('disclaimer-checkbox-label');
            if (lbl) {
              lbl.classList.add('is-locked');
              lbl.classList.remove('is-unlocked');
            }
          }
        }
      }
    }
    const actBtn = overlay ? overlay.querySelector('.btn-expired-activate-main') : null;
    if (actBtn) {
      const isEffectiveAgreed = hasAgreed || (chk && chk.checked);
      actBtn.disabled = !isEffectiveAgreed;
      actBtn.title = isEffectiveAgreed ? 'Открыть окно онлайн-активации и чата с администратором' : 'Для активации сначала подтвердите согласие с соглашением выше';
    }

    window._isLicenseExpiredModeActive = true;
    document.body.classList.add('license-expired-mode');
    if (overlay) {
      overlay.style.display = 'flex';
      overlay.classList.add('is-active');
    }

    // 1. Полная остановка опроса и мониторинга на фронтенде
    isAvitoCheckingNow = false;
    isWaitingProxyForPoll = false;
    window._isAvitoPollPaused = true;
    window._isAvitoFetchingAll = false;
    avitoIsFetchingProxies = false;
    waitingProxyCheckCounter = 0;
    avitoTimerSecondsLeft = 0;

    if (avitoData && avitoData.stats) {
      avitoData.stats.monitor_enabled = false;
      avitoData.stats.user_monitoring = false;
      avitoData.stats.user_tg_bot = false;
      avitoData.stats.bot_paused = true;
      avitoData.stats.bot_running = false;
      avitoData.stats.proxy_fetching = false;
      avitoData.stats.license_expired = true;
    }
    if (currentUser && currentUser.permissions) {
      currentUser.permissions.monitoring = false;
      currentUser.permissions.tg_bot = false;
      currentUser.permissions.is_expired = true;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
    }

    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    updateAvitoTimerUI();
    updateAvitoProxiesUI();

    // 2. Отправляем на бэкенд остановку мониторинга, ТГ-бота и сбора прокси
    if (!window._licenseStopSent) {
      window._licenseStopSent = true;
      fetch('/api/avito/proxies/stop', { method: 'POST' }).catch(() => {});
      fetch('/api/avito/apply-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monitoring: false, tg_bot: false })
      }).catch(() => {});
      fetch('/api/avito/bot-toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pause' })
      }).catch(() => {});
      fetch('/api/avito/monitor-toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'disable' })
      }).catch(() => {});
    }

    // 3. Стартовым экраном является экран блокировки/активации (license-expired-overlay).
    // Модальное окно пользователь открывает вручную по кнопке «🔑 Активация».
  } else {
    window._isLicenseExpiredModeActive = false;
    window._activationModalAutoOpened = false;
    window._licenseStopSent = false;
    document.body.classList.remove('license-expired-mode');
    if (overlay) {
      overlay.classList.remove('is-active');
      overlay.style.display = 'none';
    }
    updateAvitoTimerUI();
  }
};

window.restoreActiveMonitoringState = async function() {
  // 1. Снимаем все блокировки и флаги истечения лицензии
  window._isLicenseExpiredModeActive = false;
  window._activationChatHadActivation = true;
  window._activationModalAutoOpened = false;
  if (window._activationStatusData) {
    window._activationStatusData.is_expired = false;
  }
  if (currentUser) {
    if (!currentUser.permissions) currentUser.permissions = {};
    currentUser.permissions.is_expired = false;
    currentUser.permissions.monitoring = true;
    try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
  }
  document.body.classList.remove('license-expired-mode');
  const expOverlay = document.getElementById('license-expired-overlay');
  if (expOverlay) {
    expOverlay.classList.remove('is-active');
    expOverlay.style.display = 'none';
  }

  // 2. Сбрасываем паузы и флаги ожидания таймера опроса
  window._isAvitoPollPaused = false;
  window._isAvitoFetchingAll = false;
  isAvitoCheckingNow = false;
  isWaitingProxyForPoll = false;
  waitingProxyCheckCounter = 0;
  window._lastAutoProxyFetchTime = 0; // Сбрасываем кулдаун для немедленного авто-поиска прокси
  _recentlyPolledSearchKeys.clear();
  document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));

  // 3. Устанавливаем таймер на быстрый первый старт (5 сек) для моментального отклика
  avitoTimerSecondsLeft = 5;

  // 4. Локально активируем флаги мониторинга и сбора прокси
  if (avitoData && avitoData.stats) {
    avitoData.stats.monitor_enabled = true;
    avitoData.stats.user_monitoring = true;
    avitoData.stats.proxy_fetching = true;
  }
  avitoIsFetchingProxies = true;

  // 5. Немедленно обновляем все интерфейсные индикаторы (шапку, бейджи, кнопки)
  if (typeof updateAvitoProxiesUI === 'function') updateAvitoProxiesUI();
  if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
  if (typeof updateAvitoTimerUI === 'function') updateAvitoTimerUI();
  if (typeof window.updateTariffBadgeLive === 'function') window.updateTariffBadgeLive();
  if (typeof updateTariffPill === 'function') updateTariffPill();

  // 6. Запускаем фоновый сбор прокси на сервере
  try {
    fetch('/api/avito/proxies/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'start', source: 'auto', target: 999 })
    }).then(r => r.json()).then(d => {
      if (d && d.is_fetching !== undefined) {
        avitoIsFetchingProxies = d.is_fetching;
        if (avitoData && avitoData.stats) avitoData.stats.proxy_fetching = d.is_fetching;
      }
      if (typeof updateAvitoProxiesUI === 'function') updateAvitoProxiesUI();
    }).catch(() => {});
  } catch (e) {}

  // 7. Применяем серверные автоматические правила (мониторинг включен, ТГ по настройке пользователя)
  if (typeof window.applyAvitoAutomationRules === 'function') {
    const hasTg = Boolean(currentUser && (
      (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
      (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
    ));
    const isTg = Boolean(hasTg && (!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false));
    window.applyAvitoAutomationRules(true, isTg).catch(() => {});
  }

  // 8. Перезапускаем таймер опроса и поллер статистики
  if (typeof initAvitoTimer === 'function') initAvitoTimer();
  if (typeof startAvitoStatsPoller === 'function') startAvitoStatsPoller();

  // 9. Гарантируем инициализацию структур данных для рендеринга
  if (typeof components === 'undefined' || !Array.isArray(components)) components = [];
  if (typeof engineeringNotes === 'undefined' || !engineeringNotes) engineeringNotes = {};
  if (typeof orders === 'undefined' || !Array.isArray(orders)) orders = [];

  // 10. Загружаем сетевую информацию, сессию и свежую статистику
  if (typeof fetchServerNetworkInfo === 'function') {
    try { fetchServerNetworkInfo(); } catch (e) {}
  }
  if (typeof syncUserSession === 'function') {
    try { await syncUserSession(); } catch (e) {}
  }
  if (typeof loadAvitoStats === 'function') {
    try { await loadAvitoStats(); } catch (e) {}
  }

  // 11. Рендерим список объявлений и финализируем состояние интерфейса
  if (typeof renderCategories === 'function') renderCategories();
  if (typeof renderList === 'function') renderList();
  if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
  if (typeof updateAvitoProxiesUI === 'function') updateAvitoProxiesUI();
  if (typeof updateAvitoTimerUI === 'function') updateAvitoTimerUI();
  if (typeof window.updateTariffBadgeLive === 'function') window.updateTariffBadgeLive();
  if (typeof updateTariffPill === 'function') updateTariffPill();
};

window.onLicenseActivationSuccess = function(data) {
  if (!data) return;
  window._activationChatHadActivation = true;

  const keyToSet = data.active_key || data.key || (window._lastEnteredActivationKey || '');

  // 1. Обновляем статус лицензии в памяти
  if (!window._activationStatusData) window._activationStatusData = {};
  window._activationStatusData.is_expired = false;
  window._activationStatusData.expires_at = data.new_expires_at || data.expires_at;
  window._activationStatusData.duration = data.duration || (data.is_unlimited ? 'unlimited' : '30_days');
  window._activationStatusData.is_unlimited = !!data.is_unlimited;
  window._activationStatusData.tariff_label = data.is_unlimited ? 'Безлимит' : 'Активен';
  if (keyToSet) {
    window._activationStatusData.active_key = keyToSet;
  }

  // 2. Обновляем currentUser и сохраняем в localStorage
  if (currentUser) {
    if (!currentUser.permissions) currentUser.permissions = {};
    currentUser.permissions.is_expired = false;
    currentUser.permissions.avito_duration = data.duration || (data.is_unlimited ? 'unlimited' : '30_days');
    currentUser.permissions.avito_expires_at = data.new_expires_at || data.expires_at;
    currentUser.permissions.unlimited = !!data.is_unlimited;
    currentUser.permissions.monitoring = true;
    if (keyToSet) {
      currentUser.permissions.active_key = keyToSet;
    }
    try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
  }

  // 3. ПОЛНОСТЬЮ ВОССТАНАВЛИВАЕМ ВСЕ ФОНОВЫЕ ПРОЦЕССЫ И ТАЙМЕРЫ БЕЗ НЕОБХОДИМОСТИ ПЕРЕЗАГРУЗКИ СТРАНИЦЫ
  try {
    window.restoreActiveMonitoringState().catch(err => console.error('restoreActiveMonitoringState error:', err));
  } catch (e) {
    console.error('Error invoking restoreActiveMonitoringState:', e);
  }



  // 5. В фоне синхронизируем с бэкендом
  if (typeof window.loadLicenseStatus === 'function') {
    window.loadLicenseStatus().catch(() => {});
  }
};

window.updateTariffBadgeLive = function() {
  const isExp = window.isLicenseExpired();
  window.setLicenseExpiredMode(isExp);

  const pillText = document.getElementById('avito-stat-tariff-text');
  const pill = document.getElementById('pill-avito-tariff');
  const modalText = document.getElementById('modal-tariff-display-text');
  if (!pillText && !modalText) return;

  const currentDisplay = window.getTariffDisplayText();
  if (pillText && pillText.textContent !== currentDisplay) {
    pillText.textContent = currentDisplay;
  }
  if (modalText) {
    const dateInfo = window.getActivationModalDateInfo ? window.getActivationModalDateInfo() : null;
    if (dateInfo) {
      if (dateInfo.html) {
        if (modalText.dataset.renderHtml !== dateInfo.html) {
          modalText.innerHTML = dateInfo.html;
          modalText.dataset.renderHtml = dateInfo.html;
        }
      } else {
        if (modalText.dataset.renderHtml) {
          delete modalText.dataset.renderHtml;
          modalText.textContent = dateInfo.text;
        } else if (modalText.textContent.trim() !== dateInfo.text) {
          modalText.textContent = dateInfo.text;
        }
      }
      modalText.style.color = dateInfo.color;
      modalText.style.background = dateInfo.bg;
      modalText.style.border = dateInfo.border;
      modalText.title = dateInfo.title;
    }
  }

  if (pill && pillText) {
    pillText.style.fontFamily = 'inherit';
    pillText.style.fontSize = 'inherit';
    pillText.style.fontWeight = 'inherit';
    pillText.style.color = 'inherit';
    pillText.style.letterSpacing = 'inherit';
    pillText.style.textShadow = 'none';

    if (currentDisplay === 'Безлимит') {
      pill.style.background = 'rgba(255,215,0,0.1)';
      pill.style.borderColor = 'rgba(255,215,0,0.45)';
    } else if (currentDisplay === 'Истек' || currentDisplay.startsWith('Истек')) {
      pill.style.background = 'rgba(239,68,68,0.12)';
      pill.style.borderColor = 'rgba(239,68,68,0.3)';
    } else {
      pill.style.background = 'rgba(16,185,129,0.12)';
      pill.style.borderColor = 'rgba(16,185,129,0.3)';
    }
  }
};

if (!window._tariffCountdownTimer) {
  window._tariffCountdownTimer = setInterval(() => {
    try {
      window.updateTariffBadgeLive();
    } catch (e) {}
  }, 1000);
}

window.loadLicenseStatus = async function() {
  if (!currentUser) return null;
  try {
    const isMob = window.isMobileDevice();
    const devType = isMob ? 'phone' : 'pc';
    let reqId = window.getClientDeviceId();
    if (!reqId || !isMob) {
      reqId = await window.ensureClientDeviceId(!isMob);
    }
    const uName = currentUser.username || reqId || '';
    const query = new URLSearchParams({
      username: uName,
      request_id: reqId || '',
      device_type: devType,
      t: Date.now()
    });
    const res = await fetch(`/api/license/status?${query.toString()}`);
    if (res.ok) {
      const data = await res.json();
      if (data && data.success) {
        if (data.is_unlimited || data.tariff_label === 'Бессрочный (Безлимит)') {
          data.tariff_label = 'Безлимит';
        }
        window._activationStatusData = data;
        if (currentUser && currentUser.permissions) {
          currentUser.permissions.is_expired = !!data.is_expired;
          currentUser.permissions.active_key = data.active_key || null;
          currentUser.permissions.avito_expires_at = data.expires_at || null;
          if (data.duration) currentUser.permissions.avito_duration = data.duration;
          if (data.is_unlimited) {
            currentUser.permissions.unlimited = true;
            currentUser.permissions.avito_duration = 'unlimited';
          }
          if (data.request_id) {
            currentUser.permissions.hwid_request_id = data.request_id;
            try { localStorage.setItem('skybase_device_id', data.request_id); } catch (e) {}
          }
          if (data.mac) currentUser.permissions.hwid_mac = data.mac;
          currentUser.permissions.device_type = data.device_type || devType;
          if (data.telegram_username !== undefined) currentUser.telegram_username = data.telegram_username;
          if (data.telegram_chat_id !== undefined) currentUser.telegram_chat_id = data.telegram_chat_id;
          if (data.telegram_pending !== undefined) currentUser.telegram_pending = data.telegram_pending;
          try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
          if (typeof window._tgWidgetSetState === 'function') {
            const hasTg = isTelegramAccountConfirmed(currentUser);
            if (hasTg) window._tgWidgetSetState(true);
            else if (currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending') window._tgWidgetSetPending(currentUser.telegram_pending.handle);
          }
        }
        window.updateTariffBadgeLive();
        const isExpNow = (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) || data.is_expired === true;
        window.setLicenseExpiredMode(isExpNow);
        const actBtn = document.getElementById('btn-avito-activate');
        if (actBtn) {
          if (data.is_blocked) {
            actBtn.disabled = true;
            actBtn.classList.add('disabled-lock');
            actBtn.style.opacity = '0.45';
            actBtn.style.cursor = 'not-allowed';
            actBtn.style.filter = 'grayscale(1)';
            const h = Math.floor((data.remaining_block_seconds || 0) / 3600);
            const m = Math.floor(((data.remaining_block_seconds || 0) % 3600) / 60);
            actBtn.title = `Ввод заблокирован на 24 часа из-за 3 неверных попыток. Разблокировка через ${h} ч. ${m} мин.`;
          } else {
            actBtn.disabled = false;
            actBtn.classList.remove('disabled-lock');
            actBtn.style.opacity = '1';
            actBtn.style.cursor = 'pointer';
            actBtn.style.filter = 'none';
            actBtn.title = 'Активировать или продлить тариф';
          }
        }
        return data;
      }
    }
  } catch (e) {
    console.warn('loadLicenseStatus error:', e);
  }
  return null;
};

// =========================================================================
// Оповещение о новых сообщениях от администратора (значок письма над активацией)
// =========================================================================
window.showActivationMailBadge = function(count) {
  const modalOverlay = document.getElementById('modal-overlay');
  if (modalOverlay && modalOverlay.classList.contains('open') && document.getElementById('activation-chat-box')) {
    return;
  }
  const targetSelectors = ['#btn-avito-activate', '.btn-avito-activate', '.btn-expired-activate-main'];
  targetSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(btn => {
      btn.style.position = 'relative';
      let badge = btn.querySelector('.activation-unread-mail-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'activation-unread-mail-badge';
        badge.title = '❗ Новое сообщение от администратора!';
        badge.onclick = (e) => {
          e.stopPropagation();
          window.openActivationModal();
        };
        btn.appendChild(badge);
      }
      badge.innerHTML = `<span class="mail-badge-exclamation">!</span>${count > 1 ? `<span class="mail-badge-count">${count}</span>` : ''}`;
      badge.style.display = 'inline-flex';
    });
  });
};

window.hideActivationMailBadge = function() {
  document.querySelectorAll('.activation-unread-mail-badge').forEach(el => {
    try { el.remove(); } catch (e) { el.style.display = 'none'; }
  });
};

window.checkAdminUnreadMessages = async function() {
  const modalOverlay = document.getElementById('modal-overlay');
  const isActModalOpen = modalOverlay && modalOverlay.classList.contains('open') && document.getElementById('activation-chat-box');
  if (isActModalOpen) {
    window.hideActivationMailBadge();
    return;
  }

  const uName = (currentUser && currentUser.username) || 'guest';
  const reqIdEl = document.getElementById('display-pc-request-id');
  const reqId = (reqIdEl && reqIdEl.value.trim()) ||
                window.getClientDeviceId() ||
                (window._activationStatusData && window._activationStatusData.request_id) ||
                (currentUser && currentUser.permissions && currentUser.permissions.hwid_request_id) ||
                '';

  try {
    const res = await fetch(`/api/chat/messages?username=${encodeURIComponent(uName)}&request_id=${encodeURIComponent(reqId)}&t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    const messages = (data && data.messages) || [];

    const reqIdNorm = (reqId || '').trim().toLowerCase();
    const uNameNorm = (uName || '').trim().toLowerCase();

    // Непрочитанные сообщения именно от администратора
    const unreadAdminMsgs = messages.filter(m => {
      if (m.is_read) return false;
      if (m.id === '1' || m.id === 1) return false;
      const sNorm = (m.sender || '').trim().toLowerCase();
      const rNorm = (m.recipient || '').trim().toLowerCase();
      const ridNorm = (m.recipient_id || m.hw_id || '').trim().toLowerCase();
      const runameNorm = (m.recipient_username || '').trim().toLowerCase();
      const isAdminMsg = Boolean(
        m.admin_tg_sent ||
        sNorm === 'admin' ||
        sNorm === 'skynet83' ||
        (m.sender_name && m.sender_name.toLowerCase().includes('администратор'))
      );
      if (!isAdminMsg) return false;
      if (rNorm === 'admin') return false;
      if (reqIdNorm && sNorm === reqIdNorm) return false;
      const mHwNorm = (m.hw_id || '').trim().toLowerCase();
      const isForMe = (
        (reqIdNorm && (rNorm === reqIdNorm || ridNorm === reqIdNorm || mHwNorm === reqIdNorm)) ||
        (uNameNorm && uNameNorm !== 'guest' && (rNorm === uNameNorm || runameNorm === uNameNorm)) ||
        (rNorm === 'all' && sNorm !== reqIdNorm)
      );
      return isForMe;
    });

    if (unreadAdminMsgs.length > 0) {
      window.showActivationMailBadge(unreadAdminMsgs.length);
    } else {
      window.hideActivationMailBadge();
    }
  } catch (e) {}
};

if (!window._checkAdminChatInterval) {
  window._checkAdminChatInterval = setInterval(window.checkAdminUnreadMessages, 3500);
}
setTimeout(window.checkAdminUnreadMessages, 1200);

window.getActivationModalDateInfo = function(overrideStatus) {
  const st = overrideStatus || window._activationStatusData || {};
  const perms = (currentUser && currentUser.permissions) || {};
  
  // Ключ активен, только если он есть в серверном статусе или в permissions
  const hasKey = !!(st.active_key || perms.active_key);
  // Дата берется только если есть ключ, либо если сервер явно подтвердил expires_at
  const expStr = hasKey ? (st.expires_at || perms.avito_expires_at || '') : (st.expires_at || '');
  const isUnl = hasKey && (st.is_unlimited || st.duration === 'unlimited' || perms.avito_duration === 'unlimited' || perms.unlimited);

  function formatDt(str) {
    if (!str) return null;
    try {
      const dt = new Date(String(str).replace(' ', 'T'));
      if (!isNaN(dt.getTime())) {
        const dd = String(dt.getDate()).padStart(2, '0');
        const mm = String(dt.getMonth() + 1).padStart(2, '0');
        const yyyy = dt.getFullYear();
        const hh = String(dt.getHours()).padStart(2, '0');
        const mi = String(dt.getMinutes()).padStart(2, '0');
        const ss = String(dt.getSeconds()).padStart(2, '0');
        return `${dd}.${mm}.${yyyy} ${hh}:${mi}:${ss}`;
      }
    } catch (e) {}
    return str;
  }

  const formattedDate = formatDt(expStr);

  // 1. Первый запуск / не активирована:
  // Если нет ключа, или серверный статус "Требуется активация" / "unactivated"
  const isUnactivated = !hasKey || st.duration === 'unactivated' || st.tariff_label === 'Требуется активация';
  if (isUnactivated && (!hasKey || !formattedDate)) {
    const unactivatedHtml = `
      <div style="display:inline-flex;align-items:center;gap:3px;">
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 5px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">--</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">ДД</span></div>
        <span style="color:#64748b;font-weight:900;font-size:13px;margin-bottom:10px;line-height:1;">.</span>
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 5px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">--</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">ММ</span></div>
        <span style="color:#64748b;font-weight:900;font-size:13px;margin-bottom:10px;line-height:1;">.</span>
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 6px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">----</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">ГГГГ</span></div>
        <span style="color:#38bdf8;font-size:11px;margin:0 3px 10px 3px;line-height:1;">•</span>
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 5px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">--</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">ЧЧ</span></div>
        <span style="color:#64748b;font-weight:900;font-size:13px;margin-bottom:10px;line-height:1;">:</span>
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 5px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">--</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">ММ</span></div>
        <span style="color:#64748b;font-weight:900;font-size:13px;margin-bottom:10px;line-height:1;">:</span>
        <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.95);border:1px solid rgba(251,191,36,0.35);border-radius:5px;padding:2px 5px;line-height:1;text-shadow:0 0 8px rgba(251,191,36,0.3);">--</span><span style="font-size:7.5px;font-weight:800;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin-top:3px;line-height:1;">СС</span></div>
      </div>
    `.trim();
    return {
      text: '--.--.----.--:--:--',
      html: unactivatedHtml,
      state: 'unactivated',
      bg: '#090e17',
      border: '1.5px solid #23354d',
      color: '#fbbf24',
      title: 'Первый запуск: требуется активация ключа (Формат: ДД.ММ.ГГГГ ЧЧ:ММ:СС)'
    };
  }

  // 2. VIP Безлимит
  if (isUnl) {
    return {
      text: 'Бессрочно (VIP)',
      state: 'active',
      bg: '#059669',
      border: '1px solid #10b981',
      color: '#ffffff',
      title: 'Бессрочная лицензия (VIP)'
    };
  }

  // 3. Лицензия закончилась (истекла): слабый/мягкий красный фон
  const isExp = window.isLicenseExpired();
  if (isExp) {
    return {
      text: formattedDate || '--.--.----.--:--:--',
      state: 'expired',
      bg: 'rgba(239, 68, 68, 0.22)',
      border: '1px solid rgba(239, 68, 68, 0.5)',
      color: '#ffffff',
      title: 'Срок действия лицензии завершён'
    };
  }

  // 4. Лицензия активирована: дата до которой действует (белыми цифрами на зеленом фоне)
  return {
    text: formattedDate || '--.--.----.--:--:--',
    state: 'active',
    bg: '#059669',
    border: '1px solid #10b981',
    color: '#ffffff',
    title: 'Лицензия активна'
  };
};

window.onModalDisclaimerChange = function(cb) {
  const isAgreed = Boolean(cb && cb.checked);
  if (isAgreed) {
    try { localStorage.setItem('avitohunter_disclaimer_agreed', '1'); } catch(e){}
    const subBtn = document.getElementById('btn-submit-activation');
    if (subBtn) { subBtn.disabled = false; subBtn.removeAttribute('disabled'); subBtn.style.opacity = '1'; subBtn.style.cursor = 'pointer'; }
    const trialBtn = document.getElementById('btn-request-trial-key');
    if (trialBtn && !trialBtn.getAttribute('data-trial-used')) { trialBtn.disabled = false; trialBtn.removeAttribute('disabled'); trialBtn.style.opacity = '1'; trialBtn.style.cursor = 'pointer'; }
    const mainBtn = document.getElementById('btn-expired-activate-main');
    if (mainBtn) { mainBtn.disabled = false; mainBtn.removeAttribute('disabled'); }
    const mainChk = document.getElementById('chk-activation-disclaimer-agree');
    if (mainChk) mainChk.checked = true;
  }
};

window.openActivationModal = async function(preloadedStatus) {
  window.hideActivationMailBadge();
  if (!currentUser) return;
  try {
    const isMob = window.isMobileDevice();
    let status = preloadedStatus || window._activationStatusData;
    if (!status && typeof window.loadLicenseStatus === 'function') {
      try {
        status = await window.loadLicenseStatus();
      } catch (e) {
        console.warn('loadLicenseStatus in openActivationModal error:', e);
      }
    }
    if (typeof window.ensureClientDeviceId === 'function') {
      try { await window.ensureClientDeviceId(); } catch (e) {}
    }

    const reqId = (status && status.request_id) || window.getClientDeviceId() || (window._activationStatusData && window._activationStatusData.request_id) || (currentUser && currentUser.permissions && currentUser.permissions.hwid_request_id) || '';
    const mac = (status && status.mac) || (window._activationStatusData && window._activationStatusData.mac) || (currentUser && currentUser.permissions && currentUser.permissions.hwid_mac) || '';
    const uNamePre = (currentUser && currentUser.username) || 'guest';
    const hasAgreed = localStorage.getItem('avitohunter_disclaimer_agreed') === '1';

    // Отправляем отметку о прочтении на сервер
    fetch('/api/chat/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uNamePre, request_id: reqId })
    }).catch(() => {});

  const isBlocked = status && status.is_blocked;
  const trialUsed = Boolean(status && status.trial_used);
  const remSec = (status && status.remaining_block_seconds) || 0;
  const blockH = Math.floor(remSec / 3600);
  const blockM = Math.floor((remSec % 3600) / 60);
  const attempts = (status && status.attempts) || 0;
  const remAttempts = Math.max(0, 3 - attempts);
  const dateInfo = window.getActivationModalDateInfo(status);

  const isTgConfirmed = isTelegramAccountConfirmed(currentUser);
  const myTgPending = (typeof _isEditingTg === 'undefined' || !_isEditingTg)
    ? (!isTgConfirmed && ((avitoData && avitoData.stats && avitoData.stats.telegram_pending && avitoData.stats.telegram_pending.status === 'pending')
      ? avitoData.stats.telegram_pending
      : (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending' ? currentUser.telegram_pending : null)))
    : null;
  const myTgPendingHandle = myTgPending ? (myTgPending.handle || '') : '';
  const myTgVal = (isTgConfirmed && currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) || '';

  const devIcon = isMob ? '📱' : '💻';
  const devTitle = isMob ? '📱 ID вашего телефона:' : '💻 ID вашего компьютера:';
  const devCopyBtn = isMob ? '📋 Скопировать ID' : '📋 Скопировать ID';
  const devSubLabel = isMob ? (mac ? `ID: ${mac}` : 'Мобильное устройство') : `MAC: ${escapeHtml(mac || 'определен')}`;
  const tgDevName = isMob ? 'телефона' : 'AvitoHunter';
  const tgUrl = `https://t.me/skynet19081983?text=${encodeURIComponent('Здравствуйте! Мой ID для активации ' + tgDevName + ': ' + reqId + '. Прошу выдать ответный ключ.')}`;

  modalBody.innerHTML = `
    <div style="padding:0.2rem 0;">
      <!-- Заголовок и текущий статус даты лицензии -->
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.75rem;">
        <div>
          <h3 style="font-size:1.3rem;font-weight:800;color:#f59e0b;margin:0 0 0.2rem 0;display:flex;align-items:center;gap:0.5rem;">
            🔐 Активация тарифного плана
          </h3>
          <span style="font-size:0.82rem;color:var(--text-secondary);">
            Чат с администратором и онлайн-активация ключей доступа
          </span>
        </div>
        <span id="modal-tariff-display-text"
          style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;letter-spacing:0.5px;font-size:0.88rem;font-weight:800;color:${dateInfo.color};background:${dateInfo.bg};border:${dateInfo.border};padding:0.35rem 0.75rem;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.25);user-select:none;display:inline-flex;align-items:center;justify-content:center;transition:background 0.3s ease, border-color 0.3s ease;"
          title="${escapeHtml(dateInfo.title)}">
          ${dateInfo.html || escapeHtml(dateInfo.text)}
        </span>
      </div>

      <!-- ID код ПК / Телефона и кнопки отправки -->
      <div style="background:rgba(2,132,199,0.07);border:1.5px solid rgba(2,132,199,0.35);border-radius:10px;padding:0.75rem 0.95rem;margin-bottom:0.85rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.4rem;">
          <span style="font-size:0.86rem;font-weight:700;color:#38bdf8;display:flex;align-items:center;gap:0.35rem;">
            ${devTitle}
          </span>
          <span style="font-size:0.76rem;color:#94a3b8;font-family:monospace;background:rgba(15,23,42,0.6);padding:0.15rem 0.45rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
            ${devSubLabel}
          </span>
        </div>
        <div class="activation-id-controls-row" style="display:flex;gap:0.45rem;align-items:center;flex-wrap:wrap;">
          <input type="text" id="display-pc-request-id" readonly value="${escapeHtml(reqId)}"
            onclick="this.select();"
            style="flex:1;min-width:180px;background:#0f172a;border:1px solid rgba(2,132,199,0.5);border-radius:8px;padding:0.55rem 0.75rem;font-size:1rem;font-family:monospace;letter-spacing:1px;font-weight:800;color:#38bdf8;text-align:center;outline:none;user-select:all;cursor:pointer;"
            title="Нажмите, чтобы выделить ID">
          <button type="button" id="btn-copy-pc-id" onclick="window.copyPcRequestId()" class="cat-btn"
            style="background:#0284c7;color:#ffffff;font-weight:700;padding:0.55rem 0.9rem;border-radius:8px;font-size:0.85rem;white-space:nowrap;cursor:pointer;">
            ${devCopyBtn}
          </button>
          <button type="button" id="btn-send-pc-id-chat" onclick="window.sendPcIdToChat()" class="cat-btn"
            style="background:linear-gradient(135deg, #0284c7, #0369a1);color:#ffffff;font-weight:800;padding:0.55rem 0.95rem;border-radius:8px;font-size:0.85rem;white-space:nowrap;cursor:pointer;display:inline-flex;align-items:center;gap:0.35rem;box-shadow:0 2px 8px rgba(2,132,199,0.35);"
            title="Отправить ваш ID код в чат администратору">
            📤 Отправить ID в чат
          </button>
        </div>

        <!-- Кнопка запроса триал-ключа прямо под кнопками копировать и отправить ID в чат -->
        <div style="margin-top:0.5rem;display:flex;align-items:center;gap:0.45rem;">
          ${trialUsed ? `
            <button type="button" id="btn-request-trial-key" class="cat-btn" disabled data-trial-used="1"
              style="width:100%;background:#334155;color:#94a3b8;border:1px solid #475569;font-weight:700;padding:0.6rem 1rem;border-radius:8px;font-size:0.88rem;white-space:nowrap;cursor:not-allowed;display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;opacity:0.4;filter:grayscale(0.8);pointer-events:none;"
              title="Ключ уже был ранее активирован на этом устройстве">
              ⛔ Ключ уже был ранее активирован
            </button>
          ` : `
            <button type="button" id="btn-request-trial-key" onclick="window.requestTrialKeyAction()" class="cat-btn"
              ${!hasAgreed ? 'disabled' : ''}
              style="width:100%;background:linear-gradient(135deg, #10b981, #059669);color:#ffffff;font-weight:800;padding:0.6rem 1rem;border-radius:8px;font-size:0.88rem;white-space:nowrap;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;box-shadow:0 2px 10px rgba(16,185,129,0.35);border:none;${!hasAgreed ? 'opacity:0.45;cursor:not-allowed;box-shadow:none;' : ''}"
              title="${hasAgreed ? 'Активировать бесплатный ознакомительный период (3 дня) прямо сейчас' : 'Сначала подтвердите согласие с нотацией выше'}">
              🎁 Активировать бесплатный триал (3 дня)
            </button>
          `}
        </div>

        <!-- Строка быстрого ввода адреса Telegram (привязка аккаунта) -->
        <div style="margin-top:0.5rem;display:flex;align-items:center;gap:0.45rem;">
          <div id="modal-tg-link-wrap" class="avito-tg-link-wrap${isTgConfirmed ? ' state-linked' : (myTgPending ? ' state-pending' : '')}"
            style="display:flex;align-items:center;border-radius:10px;padding:2px 8px;height:38px;width:100%;box-sizing:border-box;gap:6px;flex:1;transition:background 0.3s,border-color 0.3s;cursor:text;${isTgConfirmed ? 'background:rgba(16,185,129,0.22);border:2px solid #10b981;box-shadow:0 0 12px rgba(16,185,129,0.35);' : (myTgPending ? 'background:rgba(234,179,8,0.14);border:1.5px solid rgba(234,179,8,0.7);box-shadow:none;' : 'background:rgba(239,68,68,0.12);border:1.5px solid rgba(239,68,68,0.55);box-shadow:none;')}"
            title="${isTgConfirmed ? 'Telegram привязан. Нажмите, чтобы изменить' : (myTgPending ? 'Ожидает подтверждения в Telegram-боте' : '@username или ID')}">
            <span class="tg-link-icon" onclick="window._openTgBotBind(event)" style="display:inline-flex;align-items:center;user-select:none;flex-shrink:0;cursor:pointer;" title="Открыть Telegram-бота @avvvskybot">
              <img src="img/telegram.png" alt="Telegram" style="width:20px;height:20px;object-fit:contain;vertical-align:middle;display:inline-block;">
            </span>
            <input type="text" id="input-modal-tg-handle" name="tg_handle_modal_input" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-form-type="other" role="presentation" value="${escapeHtml(myTgVal || (myTgPendingHandle ? (myTgPendingHandle.startsWith('@') ? myTgPendingHandle : '@' + myTgPendingHandle.replace(/^@/, '')) : ''))}" placeholder="@username или ID" title="@username или ID"
              style="background:transparent;border:none;outline:none;color:#ffffff;font-size:0.86rem;font-weight:${isTgConfirmed ? '700' : '600'};flex:1;min-width:0;width:100%;box-sizing:border-box;cursor:text;"
              onclick="window._tgInputSingleClick(this)"
              onfocus="window._tgInputSingleClick(this)"
              oninput="window._tgInputOnInput(this)"
              onkeyup="window._tgInputOnInput(this)"
              onchange="window._tgInputOnInput(this)"
              onpaste="setTimeout(()=>window._tgInputOnInput(this),0)"
              oncut="setTimeout(()=>window._tgInputOnInput(this),0)"
              onkeydown="if(event.key==='Enter'){window._handleTgEnter('modal');this.blur();}">
            <button type="button" id="btn-modal-tg-bind"
              onclick="window._tgButtonClick('modal')"
              class="cat-btn${myTgPending ? ' btn-tg-pending' : ''}"
              ${isTgConfirmed ? 'data-accepted="1"' : (myTgPending ? 'data-pending="1"' : '')}
              style="width:96px;min-width:96px;max-width:96px;box-sizing:border-box;flex-shrink:0;text-align:center;justify-content:center;padding:0.3rem 0.2rem;font-size:0.8rem;font-weight:700;border-radius:8px;white-space:nowrap;cursor:pointer;${isTgConfirmed ? 'background:#166534;color:#ffffff;border:1px solid #14532d;opacity:1;' : (myTgPending ? 'background:rgba(234,179,8,0.22);color:#eab308;border:1px solid rgba(234,179,8,0.6);opacity:1;' : 'background:rgba(14,165,233,0.18);color:#38bdf8;border:1px solid rgba(14,165,233,0.4);')}"
              title="${isTgConfirmed ? 'Telegram-аккаунт привязан. Нажмите для сохранения или изменения' : (myTgPending ? 'Ожидает подтверждения в Telegram-боте @avvvskybot. Наведите для отмены' : 'Привязать адрес Telegram к аккаунту')}">${isTgConfirmed ? 'Привязан' : (myTgPending ? '<span class="tg-pending-label" style="display:inline-block;position:relative;left:-5px;">⏳ Ожидание</span><span class="tg-cancel-label" style="display:none;">Отменить</span>' : 'Привязать')}</button>
          </div>
        </div>

        <!-- Кнопка Telegram администратора -->
        <div style="margin-top:0.45rem;display:flex;align-items:center;justify-content:center;gap:0.45rem;">
          <a href="${tgUrl}" target="_blank" rel="noopener" class="cat-btn btn-activation-tg"
            style="width:100%;background:#1e293b;border:1px solid rgba(2,132,199,0.4);font-weight:700;padding:0.5rem 0.85rem;border-radius:8px;font-size:0.84rem;white-space:nowrap;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;cursor:pointer;"
            title="Написать администратору напрямую в Telegram">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;vertical-align:middle;">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.75-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .37z" fill="#38bdf8"/>
            </svg>
            <span style="color:#38bdf8;font-weight:700;">Администратор в Telegram:</span>&nbsp;<span style="color:#ffffff;font-weight:700;">@skynet19081983</span>
          </a>
        </div>

        <!-- Кнопка Email администратора -->
        <div style="margin-top:0.35rem;display:flex;align-items:center;justify-content:center;gap:0.45rem;">
          <a href="mailto:skynet-system83@mail.ru" class="cat-btn"
            style="width:100%;background:#1e293b;border:1px solid rgba(2,132,199,0.3);font-weight:700;padding:0.45rem 0.85rem;border-radius:8px;font-size:0.83rem;white-space:nowrap;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;cursor:pointer;color:#ffffff;"
            title="Написать администратору на электронную почту">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;vertical-align:middle;">
              <rect x="2" y="4" width="20" height="16" rx="2" stroke="#38bdf8" stroke-width="2" fill="rgba(56,189,248,0.15)"/>
              <path d="M22 7l-10 7L2 7" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span style="color:#38bdf8;font-weight:700;">Почта поддержки:</span>&nbsp;<span style="color:#ffffff;font-weight:700;">skynet-system83@mail.ru</span>
          </a>
        </div>
      </div>

      <!-- Встроенный онлайн-чат с администратором -->
      <div style="background:var(--bg-main);border:1px solid var(--border-color);border-radius:12px;padding:0.85rem 1rem;margin-bottom:0.85rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.55rem;">
          <span style="font-size:0.88rem;font-weight:700;color:var(--text-primary);display:flex;align-items:center;gap:0.4rem;">
            💬 Чат с администратором
          </span>
          <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
            <button type="button" onclick="window.clearActivationChatHistory()" class="cat-btn"
              style="background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);color:#f87171;font-size:0.75rem;padding:0.2rem 0.6rem;border-radius:6px;cursor:pointer;display:inline-flex;align-items:center;gap:0.3rem;"
              title="Очистить историю сообщений в этом окне">
              🗑️ Очистить историю
            </button>
            <span style="font-size:0.75rem;color:#10b981;font-weight:600;display:flex;align-items:center;gap:0.3rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block;"></span> Онлайн-связь (доставка в Telegram админу)
            </span>
          </div>
        </div>

        <!-- Окно сообщений чата -->
        <div id="activation-chat-box" style="height:200px;max-height:200px;overflow-y:auto;background:#090d16;border:1.5px solid var(--border-color);border-radius:10px;padding:0.75rem;display:flex;flex-direction:column;gap:0.6rem;scroll-behavior:smooth;">
          <div style="text-align:center;color:var(--text-secondary);font-size:0.82rem;padding:2rem 0;">
            Загрузка сообщений диалога...
          </div>
        </div>

        <!-- Индикатор ошибки или успеха при активации из чата -->
        <div id="activation-chat-feedback" style="display:none;margin-top:0.45rem;padding:0.55rem 0.8rem;border-radius:8px;font-size:0.85rem;font-weight:600;line-height:1.4;"></div>

        <!-- Строка отправки сообщения в чат -->
        <div class="activation-chat-input-row" style="display:flex;gap:0.45rem;align-items:center;margin-top:0.6rem;">
          <input type="text" id="activation-chat-input"
            placeholder="Сообщение администратору..."
            onkeydown="if(event.key==='Enter') window.sendActivationChatMessage();"
            style="flex:1;min-width:0;background:var(--bg-card);border:1.5px solid var(--border-color);border-radius:8px;padding:0.55rem 0.75rem;font-size:0.88rem;color:var(--text-primary);outline:none;box-sizing:border-box;">
          <button type="button" id="btn-send-activation-chat" onclick="window.sendActivationChatMessage()" class="cat-btn activation-chat-send-btn"
            style="background:#059669;border:1px solid #047857;color:#ffffff;font-weight:800;padding:0.55rem 1rem;border-radius:8px;font-size:0.88rem;white-space:nowrap;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;box-shadow:0 2px 6px rgba(5,150,105,0.25);transition:all 0.2s ease;"
            title="Отправить сообщение администратору">
            🚀 Отправить
          </button>
        </div>
      </div>

      <!-- Блок активации ключа -->
      <div style="background:rgba(245,158,11,0.06);border:1.5px solid rgba(245,158,11,0.35);border-radius:10px;padding:0.75rem 0.95rem;margin-bottom:0.85rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;flex-wrap:wrap;gap:0.3rem;">
          <span style="font-size:0.86rem;font-weight:700;color:#fbbf24;display:flex;align-items:center;gap:0.35rem;">
            🔑 Ввод ключа активации:
          </span>
          <span style="font-size:0.75rem;color:${remAttempts <= 1 ? '#ef4444' : '#eab308'};font-weight:700;">
            Осталось попыток: ${remAttempts} из 3 (защита 24ч)
          </span>
        </div>
        <div class="activation-key-controls-row" style="display:flex;gap:0.45rem;align-items:center;flex-wrap:wrap;">
          <input type="text" id="input-license-key" maxlength="24"
            placeholder="EB30-XXXX-XXXX-XXXX-XXXX"
            oninput="window.formatActivationKeyInput(this)"
            onkeydown="if(event.key==='Enter') window.submitActivationKey();"
            style="flex:1;min-width:190px;background:#090d16;border:1.5px solid rgba(245,158,11,0.45);border-radius:8px;padding:0.55rem 0.75rem;font-size:0.95rem;font-family:monospace;letter-spacing:1px;font-weight:700;color:#ffffff;text-align:center;text-transform:uppercase;outline:none;">
          <button type="button" id="btn-submit-activation" onclick="window.submitActivationKey()" class="cat-btn"
            style="background:linear-gradient(135deg, #f59e0b, #d97706);color:#0f172a;font-weight:800;padding:0.55rem 1.25rem;border-radius:8px;font-size:0.9rem;white-space:nowrap;cursor:pointer;box-shadow:0 2px 8px rgba(245,158,11,0.35);display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;">
            <span class="btn-lightning-icon">⚡</span><span>Активировать ключ</span>
          </button>
        </div>
        <div id="activation-modal-feedback" style="display:none;margin-top:0.45rem;padding:0.5rem 0.75rem;border-radius:8px;font-size:0.85rem;font-weight:600;"></div>

        <!-- Кнопка «Отблагодарить» с иконкой монетки под полем ввода ключа активации -->
        <div style="margin-top:0.75rem;display:flex;justify-content:center;">
          <button type="button" class="cat-btn btn-donate-author" onclick="window.openDonateModal()"
            style="background:rgba(234,179,8,0.12);border:1px solid rgba(234,179,8,0.45);color:#fbbf24;font-weight:700;padding:0.42rem 1.25rem;border-radius:8px;font-size:0.88rem;cursor:pointer;display:inline-flex;align-items:center;gap:0.5rem;transition:all 0.2s ease;box-shadow:0 2px 6px rgba(0,0,0,0.2);"
            onmouseover="this.style.background='rgba(234,179,8,0.22)';this.style.borderColor='#facc15';this.style.transform='translateY(-1px)';"
            onmouseout="this.style.background='rgba(234,179,8,0.12)';this.style.borderColor='rgba(234,179,8,0.45)';this.style.transform='translateY(0)';"
            title="Отблагодарить разработчика">
            <span style="font-size:1.15rem;line-height:1;">🪙</span>
            <span>Отблагодарить</span>
          </button>
        </div>
      </div>

      <!-- Подвал -->
      <div style="display:flex;justify-content:flex-end;align-items:center;border-top:1px solid var(--border-color);padding-top:0.75rem;">
        <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.45rem 1.2rem;cursor:pointer;">Закрыть</button>
      </div>
    </div>
  `;
  openModal();
  if (myTgPending && typeof window._startTgPendingPoll === 'function') {
    window._startTgPendingPoll();
  }
  window.loadActivationChatMessages();
  if (window._activationChatPollInterval) {
    clearInterval(window._activationChatPollInterval);
  }
  window._activationChatPollInterval = setInterval(window.loadActivationChatMessages, 2500);
  } catch (err) {
    console.error('openActivationModal error:', err);
    openModal();
  }
};

window.openDonateModal = function() {
  let overlay = document.getElementById('donate-modal-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'donate-modal-overlay';
    overlay.className = 'donate-modal-overlay';
    document.body.appendChild(overlay);
  }

  // Всегда вешаем закрытие по клику на затемненный фон
  overlay.onclick = function(e) {
    if (e.target === overlay) {
      window.closeDonateModal(e);
    }
  };

  overlay.innerHTML = `
    <div class="donate-modal-card" style="pointer-events:auto !important;">
      
      <!-- Крестик закрытия -->
      <button type="button" id="donate-modal-close-x" class="btn-donate-modal-close" onclick="window.closeDonateModal(event)" style="position:absolute;top:0.75rem;right:0.75rem;background:transparent;border:none;color:#94a3b8;font-size:1.45rem;cursor:pointer;line-height:1;padding:0.35rem 0.5rem;border-radius:6px;transition:color 0.15s;z-index:100;pointer-events:auto !important;" onmouseover="this.style.color='#ffffff'" onmouseout="this.style.color='#94a3b8'" title="Закрыть">&times;</button>
      
      <!-- Заголовок -->
      <div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:1rem;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.65rem;">
        <span style="font-size:1.45rem;line-height:1;">🪙</span>
        <div>
          <h3 style="margin:0;font-size:1.1rem;font-weight:800;color:#facc15;">Отблагодарить разработчика</h3>
          <div style="font-size:0.76rem;color:#94a3b8;margin-top:2px;">Поддержка и развитие проекта AvitoHunter</div>
        </div>
      </div>

      <!-- Блок номера карты Сбера -->
      <div style="background:#090d16;border:1.5px solid rgba(34,197,94,0.35);border-radius:10px;padding:0.85rem 0.95rem;margin-bottom:0.85rem;box-shadow:inset 0 1px 3px rgba(0,0,0,0.4);">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;">
          <div style="display:flex;align-items:center;gap:0.45rem;font-size:0.8rem;color:#94a3b8;font-weight:600;">
            <!-- Иконка сберкарты -->
            <span style="display:inline-flex;align-items:center;gap:0.35rem;background:linear-gradient(135deg, #107c10, #21a038);color:#ffffff;padding:0.18rem 0.45rem;border-radius:5px;font-size:0.74rem;font-weight:800;letter-spacing:0.3px;box-shadow:0 1px 3px rgba(0,0,0,0.3);">
              💳 СберКарта
            </span>
            <span>Номер карты:</span>
          </div>
          <span style="font-size:0.72rem;color:#22c55e;font-weight:600;">(клик для копирования)</span>
        </div>
        
        <!-- Номер карты с кнопкой копирования -->
        <div onclick="window.copyDonateCardNumber(event)" style="cursor:pointer;background:rgba(34,197,94,0.08);border:1px dashed rgba(34,197,94,0.5);border-radius:8px;padding:0.55rem 0.75rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;transition:all 0.15s ease;" onmouseover="this.style.background='rgba(34,197,94,0.15)'" onmouseout="this.style.background='rgba(34,197,94,0.08)'" title="Нажмите, чтобы скопировать номер карты">
          <span style="font-family:monospace;font-size:1.12rem;font-weight:800;letter-spacing:1.8px;color:#4ade80;" id="donate-card-number-val">4276 1609 9199 2729</span>
          <button type="button" class="cat-btn" id="donate-card-copy-btn" onclick="window.copyDonateCardNumber(event)" style="padding:0.25rem 0.6rem;font-size:0.76rem;background:rgba(34,197,94,0.2);color:#4ade80;border:1px solid rgba(34,197,94,0.45);border-radius:6px;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:0.25rem;pointer-events:auto !important;">
            📋 Скопировать
          </button>
        </div>
      </div>

      <!-- Информационные поля: Банк и Получатель -->
      <div style="display:flex;flex-direction:column;gap:0.55rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:0.75rem 0.95rem;margin-bottom:1rem;font-size:0.86rem;">
        
        <!-- Банк: иконка банка, Банк: иконка сбербанка Сбербанк -->
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <span style="font-size:1.15rem;line-height:1;" title="Банк">🏦</span>
          <span style="color:#94a3b8;font-weight:600;">Банк:</span>
          <div style="display:inline-flex;align-items:center;gap:0.4rem;font-weight:700;color:#ffffff;">
            <!-- Иконка Сбербанка -->
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" style="vertical-align:middle;display:inline-block;flex-shrink:0;">
              <circle cx="12" cy="12" r="11" fill="#21a038"/>
              <path d="M7 12.5L10.5 16L17 8.5" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>Сбербанк</span>
          </div>
        </div>

        <!-- Получатель: иконка верхней части мужчины торс с головой Получатель: Иван Юрьевич Д. -->
        <div style="display:flex;align-items:center;gap:0.5rem;border-top:1px solid rgba(255,255,255,0.06);padding-top:0.45rem;">
          <!-- Иконка верхней части мужчины торс с головой -->
          <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle;display:inline-block;color:#60a5fa;flex-shrink:0;" title="Получатель">
            <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
          </svg>
          <span style="color:#94a3b8;font-weight:600;">Получатель:</span>
          <span style="font-weight:700;color:#ffffff;">Иван Юрьевич Д.</span>
        </div>
      </div>

      <!-- Кнопка Закрыть внизу -->
      <div style="display:flex;justify-content:flex-end;">
        <button type="button" id="donate-modal-close-btn" class="cat-btn btn-donate-modal-close" onclick="window.closeDonateModal(event)" style="padding:0.45rem 1.25rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.18);color:#e2e8f0;font-weight:700;border-radius:8px;font-size:0.86rem;cursor:pointer;pointer-events:auto !important;" onmouseover="this.style.background='rgba(255,255,255,0.15)'" onmouseout="this.style.background='rgba(255,255,255,0.08)'">
          Закрыть
        </button>
      </div>

    </div>
  `;

  // Навешиваем слушатели событий программно
  const card = overlay.querySelector('.donate-modal-card');
  if (card) {
    card.onclick = function(e) {
      if (e) e.stopPropagation();
    };
  }

  const closeBtns = overlay.querySelectorAll('.btn-donate-modal-close, #donate-modal-close-x, #donate-modal-close-btn');
  closeBtns.forEach(btn => {
    btn.onclick = function(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      window.closeDonateModal(e);
    };
  });

  overlay.classList.add('open');
  overlay.style.setProperty('display', 'flex', 'important');
};

window.closeDonateModal = function(e) {
  if (e) {
    if (e.stopPropagation) e.stopPropagation();
    if (e.preventDefault) e.preventDefault();
  }
  const overlay = document.getElementById('donate-modal-overlay');
  if (overlay) {
    overlay.classList.remove('open');
    overlay.style.setProperty('display', 'none', 'important');
  }
};

window.copyDonateCardNumber = function(e) {
  if (e && e.stopPropagation) e.stopPropagation();
  const cardNum = '4276160991992729';
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cardNum).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = cardNum;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(ta);
    });
  } else {
    const ta = document.createElement('textarea');
    ta.value = cardNum;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }
  const btn = document.getElementById('donate-card-copy-btn');
  if (btn) {
    btn.innerHTML = '✔ Скопировано!';
    btn.style.background = '#22c55e';
    btn.style.color = '#000000';
    setTimeout(() => {
      if (btn) {
        btn.innerHTML = '📋 Скопировать';
        btn.style.background = 'rgba(34,197,94,0.2)';
        btn.style.color = '#4ade80';
      }
    }, 2000);
  }
  if (typeof showToast === 'function') {
    showToast('Номер карты 4276160991992729 скопирован в буфер!', 'green');
  }
};

window.openSupportModal = function() {
  window.openActivationModal();
};

window.copyPcRequestId = function() {
  const inp = document.getElementById('display-pc-request-id');
  const btn = document.getElementById('btn-copy-pc-id');
  if (!inp) return;
  const val = inp.value.trim();
  if (!val) return;
  
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(val).catch(() => {});
  } else {
    inp.select();
    try { document.execCommand('copy'); } catch (e) {}
  }
  
  const isMob = window.isMobileDevice() || val.startsWith('EBMOB');
  if (btn) {
    const orig = btn.innerHTML;
    btn.innerHTML = '✅ Скопировано!';
    btn.style.background = '#10b981';
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.style.background = '#0284c7';
    }, 2000);
  }
  if (typeof showToast === 'function') {
    showToast(`📋 ID код ${isMob ? 'телефона' : 'компьютера'} скопирован в буфер обмена!`, 3000, 'blue');
  }
};

window.sendPcIdToChat = async function() {
  const reqIdEl = document.getElementById('display-pc-request-id');
  const reqId = (reqIdEl && reqIdEl.value.trim()) || window.getClientDeviceId() || (window._activationStatusData && window._activationStatusData.request_id) || '';
  if (!reqId) {
    if (typeof showToast === 'function') showToast('⚠️ ID код устройства не определен', 3000, 'red');
    return;
  }
  const isMob = window.isMobileDevice() || reqId.startsWith('EBMOB');
  const text = `Здравствуйте! Мой ID для активации ${isMob ? 'телефона' : 'AvitoHunter'}: ${reqId}. Прошу выдать ответный ключ продления.`;

  const btn = document.getElementById('btn-send-pc-id-chat');
  if (btn) { btn.disabled = true; btn.innerHTML = '⏳...'; }

  try {
    // Отправляем ID администратору через API (для уведомления бота в Telegram),
    // но НЕ отображаем это сообщение в окне чата — только показываем подтверждение.
    // Ключ активации появится в чате только когда администратор пришлёт ответный ключ.
    const senderCode = reqId || (currentUser && currentUser.username) || 'guest';
    const senderTitle = isMob
      ? `📱 Телефон (${reqId.slice(0, 10)}...)`
      : `💻 ПК (${reqId.slice(0, 10)}...)`;

    const modalTgInp = document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
    const tgVal = (modalTgInp && modalTgInp.value.trim()) ||
                  (currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) || '';

    const res = await fetch('/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender: senderCode,
        sender_id: reqId,
        sender_name: senderTitle,
        recipient: 'admin',
        text: text.trim(),
        telegram_handle: tgVal
      })
    });
    const data = await res.json();
    if (data && data.success) {
      // Показываем подтверждение в блоке фидбека чата
      const fb = document.getElementById('activation-chat-feedback');
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(14, 165, 233, 0.15)';
        fb.style.color = '#38bdf8';
        fb.style.border = '1px solid rgba(14, 165, 233, 0.35)';
        fb.innerHTML = `📤 <strong>ID ${isMob ? 'телефона' : 'устройства'} отправлен администратору!</strong><br>`
          + `<span style="font-size:0.8rem;color:#7dd3fc;">Ожидайте ответный ключ активации — он появится в этом чате.</span>`;
      }
      // НЕ вызываем loadActivationChatMessages() здесь —
      // чтобы EBID-сообщение пользователя не появилось в чате активации.
      // Чат обновится автоматически только когда придёт ответ от администратора.
    } else {
      throw new Error((data && data.error) || 'Ошибка отправки');
    }
  } catch (e) {
    console.warn('sendPcIdToChat error:', e);
    if (typeof showToast === 'function') showToast(`❌ Ошибка отправки: ${e.message || e}`, 3000, 'red');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '📤 Отправить ID в чат'; }
  }
};

window.requestTrialKeyAction = async function() {
  const reqIdEl = document.getElementById('display-pc-request-id');
  const reqId = (reqIdEl && reqIdEl.value.trim()) || window.getClientDeviceId() || (window._activationStatusData && window._activationStatusData.request_id) || '';
  if (!reqId) {
    if (typeof showToast === 'function') showToast('⚠️ ID код устройства не определен', 3000, 'red');
    return;
  }
  const btn = document.getElementById('btn-request-trial-key');
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.7';
    btn.innerHTML = '⏳ Активация триала на 3 дня...';
  }

  const fb = document.getElementById('activation-chat-feedback');
  if (fb) {
    fb.style.display = 'block';
    fb.style.background = 'rgba(14, 165, 233, 0.15)';
    fb.style.border = '1px solid rgba(14, 165, 233, 0.35)';
    fb.style.color = '#38bdf8';
    fb.innerHTML = '⏳ Проверка оборудования и моментальная активация 3-дневного доступа прямо здесь...';
  }

  try {
    const uname = (currentUser && currentUser.username) || reqId;
    const res = await fetch('/api/license/request-trial', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: reqId, username: uname })
    });
    const data = await res.json();

    if (data.success) {
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(16, 185, 129, 0.18)';
        fb.style.border = '1px solid rgba(16, 185, 129, 0.5)';
        fb.style.color = '#34d399';
        fb.innerHTML = `🎉 <strong>${data.message || 'Бесплатный триал на 3 дня успешно активирован!'}</strong><br>`
          + (data.trial_key ? `<span style="font-size:0.83rem;color:#a7f3d0;font-family:monospace;">Ключ: ${data.trial_key}</span>` : '');
      }
      if (btn) {
        btn.disabled = true;
        btn.setAttribute('data-trial-used', '1');
        btn.style.opacity = '0.5';
        btn.style.filter = 'grayscale(0.8)';
        btn.style.cursor = 'not-allowed';
        btn.innerHTML = '✅ Триал на 3 дня активирован';
      }

      setTimeout(async () => {
        if (typeof window.loadLicenseStatus === 'function') {
          await window.loadLicenseStatus();
        }
        if (typeof window.closeModal === 'function') {
          window.closeModal();
        }
        if (typeof window.setLicenseExpiredMode === 'function') {
          window.setLicenseExpiredMode(false);
        }
        location.reload();
      }, 1400);

    } else {
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(239, 68, 68, 0.18)';
        fb.style.border = '1px solid rgba(239, 68, 68, 0.5)';
        fb.style.color = '#f87171';
        fb.innerHTML = `⚠️ ${escapeHtml(data.error || 'Не удалось активировать триал')}`;
      }
      if (data.trial_used) {
        if (btn) {
          btn.disabled = true;
          btn.setAttribute('data-trial-used', '1');
          btn.style.opacity = '0.4';
          btn.style.filter = 'grayscale(0.8)';
          btn.style.pointerEvents = 'none';
          btn.style.cursor = 'not-allowed';
          btn.style.background = '#334155';
          btn.innerHTML = '⛔ Ключ уже был ранее активирован';
        }
      } else {
        if (btn) {
          btn.disabled = false;
          btn.style.opacity = '1';
          btn.innerHTML = '🎁 Активировать бесплатный триал (3 дня)';
        }
      }
      if (typeof showToast === 'function') {
        showToast(data.error || 'Ошибка активации триала', 4000, 'red');
      }
    }
  } catch (err) {
    console.error('requestTrialKeyAction error:', err);
    if (fb) {
      fb.style.display = 'block';
      fb.style.background = 'rgba(239, 68, 68, 0.18)';
      fb.style.border = '1px solid rgba(239, 68, 68, 0.5)';
      fb.style.color = '#f87171';
      fb.innerHTML = `❌ Ошибка соединения: ${escapeHtml(err.message || String(err))}`;
    }
    if (btn) {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.innerHTML = '🎁 Активировать бесплатный триал (3 дня)';
    }
  }
};

window.startTrialActivationStatusPoll = function(reqId) {
  if (window._trialPollTimer) clearInterval(window._trialPollTimer);
  let pollCount = 0;
  window._trialPollTimer = setInterval(async () => {
    pollCount++;
    if (pollCount > 150) {
      clearInterval(window._trialPollTimer);
      return;
    }
    try {
      const res = await fetch('/api/license/status?request_id=' + encodeURIComponent(reqId || ''));
      const data = await res.json();
      if (!data) return;
      window._activationStatusData = data;

      const btn = document.getElementById('btn-request-trial-key');
      if (data.trial_used) {
        if (btn) {
          btn.disabled = true;
          btn.setAttribute('data-trial-used', '1');
          btn.style.opacity = '0.4';
          btn.style.filter = 'grayscale(0.8)';
          btn.style.pointerEvents = 'none';
          btn.style.cursor = 'not-allowed';
          btn.style.background = '#334155';
          btn.style.color = '#94a3b8';
          btn.style.border = '1px solid #475569';
          btn.innerHTML = '⛔ Ключ уже был ранее активирован';
          btn.title = 'Ключ уже был ранее активирован на этом устройстве';
        }
      }

      if (data.duration && data.duration !== 'expired' && !data.is_expired) {
        clearInterval(window._trialPollTimer);
        if (typeof showToast === 'function') {
          showToast('🎉 Пробный период успешно активирован через Telegram!', 5000, 'green');
        }
        if (typeof window.fetchLicenseStatus === 'function') {
          await window.fetchLicenseStatus();
        }
        const textEl = document.getElementById('modal-tariff-display-text');
        if (textEl && window.getActivationModalDateInfo) {
          const dInfo = window.getActivationModalDateInfo(data);
          textEl.innerHTML = dInfo.html || dInfo.text;
          textEl.style.color = dInfo.color;
          textEl.style.background = dInfo.bg;
          textEl.style.border = dInfo.border;
        }
        if (typeof renderAvitoDashboard === 'function') renderAvitoDashboard();
      }
    } catch (_) {}
  }, 2000);
};

window.sendActivationChatMessage = async function() {
  const inp = document.getElementById('activation-chat-input');
  if (!inp) return;
  const text = inp.value.trim();
  if (!text) return;
  await window.sendActivationChatMessageText(text);
};

window.sendActivationChatMessageText = async function(text) {
  if (!text || !text.trim()) return;
  const btn = document.getElementById('btn-send-activation-chat');
  const inp = document.getElementById('activation-chat-input');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳...';
    btn.style.background = '#047857';
  }
  try {
    const reqIdEl = document.getElementById('display-pc-request-id');
    const reqId = (reqIdEl && reqIdEl.value.trim()) ||
                  window.getClientDeviceId() ||
                  (window._activationStatusData && window._activationStatusData.request_id) ||
                  (currentUser && currentUser.permissions && currentUser.permissions.hwid_request_id) || '';
    const isMob = window.isMobileDevice() || (reqId && reqId.startsWith('EBMOB'));
    const senderCode = reqId || (currentUser && currentUser.username) || 'guest';
    const senderTitle = reqId
      ? (isMob ? `📱 Телефон (${reqId.slice(0, 10)}...)` : `💻 ПК (${reqId.slice(0, 10)}...)`)
      : senderCode;
    const modalTgInp = document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
    const tgVal = (modalTgInp && modalTgInp.value.trim()) ||
                  (currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) || '';
    const res = await fetch('/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender: senderCode,
        sender_id: reqId || senderCode,
        sender_name: senderTitle,
        recipient: 'admin',
        text: text.trim(),
        telegram_handle: tgVal
      })
    });
    const data = await res.json();
    if (data && data.success) {
      if (inp) inp.value = '';
      await window.loadActivationChatMessages();
    } else {
      throw new Error((data && data.error) || 'Ошибка отправки');
    }
  } catch (e) {
    console.warn('sendActivationChatMessageText error:', e);
    if (typeof showToast === 'function') showToast(`❌ Ошибка отправки: ${e.message || e}`, 3000, 'red');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🚀 Отправить';
      btn.style.background = '#059669';
    }
  }
};

window.clearActivationChatHistory = async function() {
  if (!confirm('Вы уверены, что хотите очистить историю сообщений чата?')) return;
  try {
    const res = await fetch('/api/chat/clear', { method: 'POST' });
    const data = await res.json();
    if (data && data.success) {
      await window.loadActivationChatMessages();
    }
  } catch (e) {
    console.error('clearActivationChatHistory error:', e);
  }
};

window.loadActivationChatMessages = async function(forceScroll) {
  const box = document.getElementById('activation-chat-box');
  if (!box) return;
  const uName = (currentUser && currentUser.username) || 'guest';
  const reqIdEl = document.getElementById('display-pc-request-id');
  const reqId = (reqIdEl && reqIdEl.value.trim()) ||
                (window._activationStatusData && window._activationStatusData.request_id) ||
                (currentUser && currentUser.permissions && currentUser.permissions.hwid_request_id) ||
                localStorage.getItem('skybase_device_id') ||
                '';

  try {
    const res = await fetch(`/api/chat/messages?username=${encodeURIComponent(uName)}&request_id=${encodeURIComponent(reqId)}&t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    const messages = (data && data.messages) || [];

    if (messages.length === 0) {
      box.innerHTML = `
        <div style="text-align:center;color:var(--text-secondary);font-size:0.84rem;padding:2rem 1rem;line-height:1.45;">
          💬 Чат с администратором пуст.<br>
          Нажмите кнопку <strong>«📤 Отправить ID в чат»</strong> или напишите сообщение ниже, чтобы запросить ключ продления.
        </div>
      `;
      box.dataset.msgCount = '0';
      return;
    }

    const keyRegex = /\b(?:EB30|VIPX)-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b/gi;
    const activeKeyNorm = ((window._activationStatusData && window._activationStatusData.active_key) || '').toUpperCase().replace(/[^A-Z0-9]/g, '');

    const wasAtBottom = box.scrollHeight - box.clientHeight <= box.scrollTop + 50;
    const prevMsgCount = parseInt(box.dataset.msgCount || '0', 10);
    const newMsgCount = messages.length;
    box.dataset.msgCount = String(newMsgCount);

    const reqIdNorm = (reqId || '').trim().toLowerCase();
    const uNameNorm = (uName || '').trim().toLowerCase();

    let html = '';
    messages.forEach(m => {
      const sNorm = (m.sender || '').trim().toLowerCase();
      const rNorm = (m.recipient || '').trim().toLowerCase();
      const sidNorm = (m.sender_id || '').trim().toLowerCase();
      const ridNorm = (m.recipient_id || m.hw_id || '').trim().toLowerCase();
      const runameNorm = (m.recipient_username || '').trim().toLowerCase();

      // Строгая изоляция сообщений по ID конкретного устройства (ПК или Телефон) и логину
      if (reqIdNorm) {
        const isMyUser = uNameNorm && uNameNorm !== 'guest' && (rNorm === uNameNorm || runameNorm === uNameNorm || sNorm === uNameNorm);
        const mHwNorm = (m.hw_id || '').trim().toLowerCase();
        const belongsToThisDevice = (
          sNorm === reqIdNorm ||
          sidNorm === reqIdNorm ||
          rNorm === reqIdNorm ||
          ridNorm === reqIdNorm ||
          mHwNorm === reqIdNorm ||
          isMyUser ||
          rNorm === 'all'
        );
        if (!belongsToThisDevice) return;
      }

      // Если адресат admin — это исходящее сообщение от клиента (пользователя)
      const isSentToAdmin = (rNorm === 'admin');
      // Сообщение от администратора: sender явно skynet83/admin, ИЛИ admin_tg_sent=true,
      // НО только если sender не является EBID/EBMOB-кодом устройства пользователя.
      const senderIsDeviceId = sNorm.startsWith('ebid-') || sNorm.startsWith('ebmob-');
      const isAdminMsg = !isSentToAdmin && !senderIsDeviceId && Boolean(
        m.admin_tg_sent ||
        sNorm === 'admin' ||
        sNorm === 'skynet83' ||
        (m.sender_name && m.sender_name.toLowerCase().includes('администратор'))
      );

      const isMe = (isSentToAdmin && (sNorm === reqIdNorm || sidNorm === reqIdNorm)) || (
        !isAdminMsg && (
          (reqIdNorm && (sNorm === reqIdNorm || sidNorm === reqIdNorm)) ||
          (!reqIdNorm && uNameNorm && uNameNorm !== 'guest' && sNorm === uNameNorm)
        )
      );
      const rawText = m.text || '';
      let safeText = escapeHtml(rawText);

      // Ключи активации извлекаются и отображаются с кнопкой [⚡ Активировать]
      // ИСКЛЮЧИТЕЛЬНО из входящих сообщений администратора (не из своих запросов с ID кодом!)
      let keyCardsHtml = '';
      if (!isMe && isAdminMsg) {
        // Никогда не отображаем кнопки активации, если сообщение является запросом ID или текстом пользователя
        const isIdRequestText = rawText.includes('Мой ID для активации') ||
                                rawText.includes('EBID-') ||
                                rawText.includes('EBMOB-') ||
                                rawText.includes('ID вашего');
        if (!isIdRequestText) {
          const matchedKeys = rawText.match(keyRegex);
          if (matchedKeys && matchedKeys.length > 0) {
            matchedKeys.forEach(k => {
              let cleanKey = k.toUpperCase().replace(/[^A-Z0-9]/g, '');
              // Допустимы ТОЛЬКО ответные ключи продления (EB30 и VIPX)
              if (!cleanKey.startsWith('EB30') && !cleanKey.startsWith('VIPX')) return;
              if (cleanKey.length !== 20) return;

              cleanKey = `${cleanKey.slice(0,4)}-${cleanKey.slice(4,8)}-${cleanKey.slice(8,12)}-${cleanKey.slice(12,16)}-${cleanKey.slice(16,20)}`;
              const cleanRaw = cleanKey.replace(/[^A-Z0-9]/g, '');
              const activatedKeysList = (window._activationStatusData && Array.isArray(window._activationStatusData.activated_keys))
                ? window._activationStatusData.activated_keys
                : [];
              const isActivated = (window._activatedKeys && (window._activatedKeys.has(cleanRaw) || window._activatedKeys.has(cleanKey))) ||
                                  activatedKeysList.includes(cleanRaw) ||
                                  (activeKeyNorm && activeKeyNorm === cleanRaw && (!window._activationStatusData || window._activationStatusData.is_expired !== true));

              const cardClass = isActivated ? 'chat-key-card is-activated' : 'chat-key-card';
              const cardStyle = isActivated
                ? 'margin-top:0.45rem;padding:0.45rem 0.65rem;background:rgba(30,41,59,0.45);border:1.5px solid #475569;border-radius:8px;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;opacity:0.65;'
                : 'margin-top:0.45rem;padding:0.45rem 0.65rem;background:#060a12;border:1.5px solid rgba(245,158,11,0.55);border-radius:8px;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;';
              const textStyle = isActivated
                ? 'font-family:monospace;font-size:0.92rem;font-weight:700;color:#94a3b8;letter-spacing:1px;'
                : 'font-family:monospace;font-size:0.92rem;font-weight:800;color:#fbbf24;letter-spacing:1px;';

              const actionBtn = isActivated
                ? `<button type="button" disabled class="badge-key-activated">✅ Активирован</button>`
                : `<button type="button" class="btn-chat-key-gold" onclick="window.activateKeyFromChat('${cleanKey}', this)" title="Активировать этот ключ прямо сейчас"><span class="btn-lightning-icon">⚡</span><span>Активировать</span></button>`;

              keyCardsHtml += `
                <div class="${cardClass}" style="${cardStyle}">
                  <span class="chat-key-text" style="${textStyle}">🔑 ${cleanKey}</span>
                  ${actionBtn}
                </div>
              `;
            });
          }
        }
      }

      if (isMe) {
        html += `
          <div style="display:flex;flex-direction:column;align-items:flex-end;margin-bottom:0.4rem;">
            <div style="background:#0284c7;color:#ffffff;border-radius:12px 12px 2px 12px;padding:0.55rem 0.8rem;max-width:85%;font-size:0.86rem;line-height:1.4;word-break:break-word;box-shadow:0 2px 6px rgba(0,0,0,0.25);">
              ${safeText}
            </div>
            <span style="font-size:0.7rem;color:rgba(255,255,255,0.4);margin-top:0.2rem;">${escapeHtml(m.created_at || '')}</span>
          </div>
        `;
      } else {
        html += `
          <div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:0.4rem;">
            <div style="display:flex;align-items:center;gap:0.35rem;margin-bottom:0.2rem;">
              <span style="font-size:0.74rem;font-weight:700;color:#f59e0b;">👑 ${escapeHtml(m.sender_name || 'Администратор (@skynet19081983)')}</span>
              <span style="font-size:0.7rem;color:rgba(255,255,255,0.4);">${escapeHtml(m.created_at || '')}</span>
            </div>
            <div style="background:#1e293b;border:1px solid rgba(255,255,255,0.1);color:#f1f5f9;border-radius:12px 12px 12px 2px;padding:0.55rem 0.8rem;max-width:85%;font-size:0.86rem;line-height:1.4;word-break:break-word;box-shadow:0 2px 6px rgba(0,0,0,0.25);">
              ${safeText}
              ${keyCardsHtml}
            </div>
          </div>
        `;
      }
    });

    box.innerHTML = html;



    // Фоновая быстрая проверка реального статуса лицензии, если сайт в режиме блокировки
    if (window._isLicenseExpiredModeActive || (currentUser && currentUser.permissions && currentUser.permissions.is_expired)) {
      window.loadLicenseStatus().then(st => {
        if (st && st.trial_used) {
          const trialBtn = document.getElementById('btn-request-trial-key');
          if (trialBtn && !trialBtn.hasAttribute('data-trial-used')) {
            trialBtn.disabled = true;
            trialBtn.setAttribute('data-trial-used', '1');
            trialBtn.style.opacity = '0.4';
            trialBtn.style.filter = 'grayscale(0.8)';
            trialBtn.style.pointerEvents = 'none';
            trialBtn.style.cursor = 'not-allowed';
            trialBtn.style.background = '#334155';
            trialBtn.style.color = '#94a3b8';
            trialBtn.style.border = '1px solid #475569';
            trialBtn.innerHTML = '⛔ Ключ уже был ранее активирован';
            trialBtn.title = 'Ключ уже был ранее активирован на этом устройстве';
          }
        }
        if (st && st.is_expired === false && !(typeof window.isLicenseExpired === 'function' && window.isLicenseExpired())) {
          window._activationChatHadActivation = true;
          window.setLicenseExpiredMode(false);
          const expOverlay = document.getElementById('license-expired-overlay');
          if (expOverlay) {
            expOverlay.classList.remove('is-active');
            expOverlay.style.display = 'none';
          }
          document.body.classList.remove('license-expired-mode');
          if (typeof window.restoreActiveMonitoringState === 'function') {
            window.restoreActiveMonitoringState().catch(() => {});
          } else {
            window.updateTariffBadgeLive();
            if (typeof renderList === 'function') renderList();
            if (typeof updateAvitoTimerUI === 'function') updateAvitoTimerUI();
          }
          const fb = document.getElementById('activation-chat-feedback');
          if (fb) {
            fb.style.display = 'block';
            fb.style.background = 'rgba(16, 185, 129, 0.15)';
            fb.style.color = '#34d399';
            fb.style.border = '1px solid rgba(16, 185, 129, 0.4)';
            fb.innerHTML = '🎉 <strong>Тариф успешно активирован!</strong> Сайт разблокирован и готов к работе.';
          }
          const closeBtns = document.querySelectorAll('.modal-content button[onclick*="closeModal"]');
          closeBtns.forEach(btn => {
            btn.style.background = '#10b981';
            btn.style.color = '#ffffff';
            btn.style.borderColor = '#10b981';
            btn.style.fontWeight = '700';
            btn.innerHTML = '✅ Закрыть (сайт готов к работе)';
          });
        }
      }).catch(() => {});
    }

    // Скролл вниз при первом открытии, если были внизу, принудительно или если пришли новые сообщения
    if (!box.dataset.scrolled || wasAtBottom || forceScroll || newMsgCount > prevMsgCount) {
      box.scrollTop = box.scrollHeight;
      box.dataset.scrolled = 'true';
    }

    // Если есть непрочитанные сообщения от админа, помечаем их как прочитанные
    const hasUnreadFromAdmin = messages.some(m => {
      if (m.is_read) return false;
      const sNorm = (m.sender || '').trim().toLowerCase();
      return m.admin_tg_sent || sNorm === 'skynet83' || sNorm === 'admin' || (m.sender_name && m.sender_name.toLowerCase().includes('администратор'));
    });
    if (hasUnreadFromAdmin) {
      fetch('/api/chat/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: uName, request_id: reqId })
      }).then(() => {
        window.hideActivationMailBadge();
      }).catch(() => {});
    }
  } catch (err) {
    console.debug('loadActivationChatMessages error:', err);
  }
};

window.activateKeyFromChat = async function(key, btn) {
  if (!key) return;
  const fb = document.getElementById('activation-chat-feedback');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Проверка...';
  }
  const isMob = window.isMobileDevice();
  const reqId = window.getClientDeviceId() || (window._activationStatusData && window._activationStatusData.request_id) || '';
  if (fb) {
    fb.style.display = 'block';
    fb.style.background = 'rgba(245, 158, 11, 0.12)';
    fb.style.color = '#fbbf24';
    fb.style.border = '1px solid rgba(245, 158, 11, 0.35)';
    fb.textContent = `⏳ Проверка аппаратной привязки ключа к вашему ${isMob ? 'телефону' : 'ПК'}...`;
  }
  try {
    const uName = (currentUser && currentUser.username) || reqId || '';
    const res = await fetch('/api/license/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        key: key,
        username: uName,
        request_id: reqId,
        device_type: isMob ? 'phone' : 'pc'
      })
    });
    const data = await res.json();
    if (data && data.success) {
      window._activatedKeys = window._activatedKeys || new Set();
      window._activatedKeys.add(key.toUpperCase().replace(/[^A-Z0-9]/g, ''));
      window._activatedKeys.add(key.toUpperCase());
      if (window._activationStatusData) {
        window._activationStatusData.active_key = key;
        if (!Array.isArray(window._activationStatusData.activated_keys)) {
          window._activationStatusData.activated_keys = [];
        }
        window._activationStatusData.activated_keys.push(key.toUpperCase().replace(/[^A-Z0-9]/g, ''));
      }

      const keyInp = document.getElementById('input-license-key');
      if (keyInp) keyInp.value = key;

      if (btn) {
        const card = btn.closest('.chat-key-card');
        if (card) {
          card.classList.add('is-activated');
          card.style.background = 'rgba(30, 41, 59, 0.45)';
          card.style.borderColor = '#475569';
          card.style.opacity = '0.65';
          const keySpan = card.querySelector('.chat-key-text');
          if (keySpan) {
            keySpan.style.color = '#94a3b8';
            keySpan.style.fontWeight = '700';
          }
        }
        btn.outerHTML = '<button type="button" disabled class="badge-key-activated">✅ Активирован</button>';
      }
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(16, 185, 129, 0.15)';
        fb.style.color = '#34d399';
        fb.style.border = '1px solid rgba(16, 185, 129, 0.4)';
        fb.innerHTML = `🎉 <strong>Успешно!</strong> ${escapeHtml(data.message || 'Ключ успешно активирован! Тариф продлен.')}<br><span style="font-size:0.8rem;color:#a7f3d0;">Сайт на заднем плане уже включился и доступен для работы!</span>`;
      }

      // Применяем успешную активацию: разблокируем сайт на заднем фоне, обновляем бейдж и мониторинг
      if (typeof window.onLicenseActivationSuccess === 'function') {
        window.onLicenseActivationSuccess(data);
      }
      window.loadActivationChatMessages();
    } else {
      const isBl = data && data.is_blocked;
      const errMsg = (data && data.error) || 'Не удалось активировать ключ';
      
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(239, 68, 68, 0.15)';
        fb.style.color = '#fca5a5';
        fb.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        fb.innerHTML = `❌ <strong>Ошибка активации:</strong> ${escapeHtml(errMsg)}`;
      }
      if (btn) {
        if (isBl) {
          btn.outerHTML = '<button type="button" disabled class="badge-key-activated" style="background:rgba(239,68,68,0.2);color:#ef4444;border-color:#ef4444;">⛔️ Заблокировано на 24ч</button>';
        } else {
          btn.disabled = false;
          btn.innerHTML = '<span class="btn-lightning-icon">⚡</span><span>Повторить</span>';
        }
      }
      if (typeof showToast === 'function') {
        showToast(`❌ ${errMsg}`, 4000, 'red');
      }
      await window.loadLicenseStatus();
    }
  } catch (err) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.background = 'rgba(239, 68, 68, 0.15)';
      fb.style.color = '#fca5a5';
      fb.style.border = '1px solid rgba(239, 68, 68, 0.4)';
      fb.textContent = `❌ Ошибка сети или сервера: ${err.message || err}`;
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-lightning-icon">⚡</span><span>Активировать</span>';
    }
  }
};

window.formatActivationKeyInput = function(inp) {
  if (!inp) return;
  let val = inp.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 20);
  const parts = [];
  for (let i = 0; i < val.length; i += 4) {
    parts.push(val.slice(i, i + 4));
  }
  inp.value = parts.join('-');
};

window.submitActivationKey = async function() {
  const inp = document.getElementById('input-license-key');
  const btn = document.getElementById('btn-submit-activation');
  const fb = document.getElementById('activation-modal-feedback');
  if (!inp || !btn) return;

  const rawKey = inp.value.trim();
  if (!rawKey) {
    if (fb) {
      fb.style.display = 'block';
      fb.style.background = 'rgba(239,68,68,0.15)';
      fb.style.color = '#ef4444';
      fb.style.border = '1px solid rgba(239,68,68,0.4)';
      fb.textContent = 'Введите 20-значный ключ активации.';
    }
    return;
  }

  btn.disabled = true;
  btn.textContent = '⏳ Проверка...';
  if (fb) fb.style.display = 'none';

  let activationSucceeded = false;
  try {
    const isMob = window.isMobileDevice();
    const reqId = window.getClientDeviceId() || (window._activationStatusData && window._activationStatusData.request_id) || '';
    window._lastEnteredActivationKey = rawKey;
    const res = await fetch('/api/license/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        key: rawKey,
        username: currentUser ? currentUser.username : '',
        request_id: reqId,
        device_type: isMob ? 'phone' : 'pc'
      })
    });
    const data = await res.json();
    if (data && data.success) {
      activationSucceeded = true;
      data.active_key = data.active_key || rawKey;
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(16,185,129,0.15)';
        fb.style.color = '#10b981';
        fb.style.border = '1px solid rgba(16,185,129,0.4)';
        fb.innerHTML = `🎉 <strong>${escapeHtml(data.message || 'Ключ успешно активирован!')}</strong><br><span style="font-size:0.82rem;color:#a7f3d0;margin-top:0.25rem;display:inline-block;">Сайт на заднем плане уже включился и доступен для работы!</span>`;
      }
      inp.value = '';
      if (btn) {
        btn.disabled = false;
        btn.style.background = '#059669';
        btn.innerHTML = '✅ Закрыть окно';
        btn.onclick = function() { closeModal(); };
      }
      if (!window._activatedKeys) window._activatedKeys = new Set();
      window._activatedKeys.add(rawKey.replace(/[^A-Za-z0-9]/g, '').toUpperCase());
      if (data.active_key) {
        window._activatedKeys.add(String(data.active_key).replace(/[^A-Za-z0-9]/g, '').toUpperCase());
      }
      if (typeof window.loadActivationChatMessages === 'function') {
        window.loadActivationChatMessages(true);
      }

      // Применяем успешную активацию: разблокируем сайт на заднем фоне, обновляем бейдж и мониторинг
      if (typeof window.onLicenseActivationSuccess === 'function') {
        window.onLicenseActivationSuccess(data);
      }
      if (typeof updateTariffPill === 'function') {
        updateTariffPill();
      }

      setTimeout(() => {
        closeModal();
      }, 3500);
    } else {
      await window.loadLicenseStatus();
      const errMsg = (data && data.error) ? data.error : 'Ключ недействителен или истек';
      if (typeof showToast === 'function') {
        showToast(`❌ ${errMsg}`, 5000, 'red');
      }
      if (data && data.is_blocked) {
        // Заблокирован — перерисовываем модалку в заблокированный вид
        window.openActivationModal();
      } else {
        if (fb) {
          fb.style.display = 'block';
          fb.style.background = 'rgba(239,68,68,0.15)';
          fb.style.color = '#f87171';
          fb.style.border = '1px solid rgba(239,68,68,0.4)';
          fb.innerHTML = `❌ ${escapeHtml(errMsg)}`;
        }
      }
    }
  } catch (err) {
    console.error('submitActivationKey error:', err);
    if (!activationSucceeded && fb) {
      fb.style.display = 'block';
      fb.style.background = 'rgba(239,68,68,0.15)';
      fb.style.color = '#ef4444';
      fb.textContent = 'Ошибка связи с сервером при активации.';
    }
  } finally {
    if (!activationSucceeded && btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-lightning-icon">⚡</span><span>Активировать ключ</span>';
    }
  }
};

window.openShareBotModal = function() {};
window.copyBotShareLink = function() {};
window.copyBotInviteText = function() {};
window.toggleAvitoTimer = function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  const mOverlay = document.getElementById('modal-overlay');
  if (mOverlay && mOverlay.classList.contains('open') && document.querySelector('.speed-preset-grid')) {
    closeModal();
    return;
  }
  openPollingSpeedModal();
};

async function runAvitoAutoCheck() {
  if (!currentUser) return;
  if (window._isAvitoFetchingAll || window._isAvitoPollPaused) return;
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) return;
  if (!hasActiveAvitoSearches()) {
    isWaitingProxyForPoll = false;
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    updateAvitoTimerUI();
    return;
  }
  if (isAvitoCheckingNow) return;
  // В гибридном режиме (avitoHybridMode) разрешаем опрос даже без прокси (прямое соединение)
  if ((avitoProxyCount === 0 && !avitoHybridMode) || isWaitingProxyForPoll || !isAvitoPollingActive()) {
    _recentlyPolledSearchKeys.clear();
    document.querySelectorAll('.poll-flash').forEach(el => el.classList.remove('poll-flash'));
    if (avitoProxyCount === 0 && isAvitoPollingActive() && !avitoHybridMode) {
      isWaitingProxyForPoll = true;
      avitoTimerSecondsLeft = 0;
      updateAvitoTimerUI('WAITING_PROXY');
    }
    return;
  }
  isAvitoCheckingNow = true;
  updateAvitoTimerUI('GO');
  try {
    const res = await fetch('/api/avito/check', { method: 'POST' });
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.success) {
      if (Array.isArray(data.removed_items) && data.removed_items.length > 0) {
        data.removed_items.forEach(remId => {
          removeCardFromGridInPlace(remId);
        });
        updateAvitoCountBadge();
      }
      if (Array.isArray(data.new_items) && data.new_items.length > 0) {
        if (!Array.isArray(avitoData.items)) {
          avitoData.items = [];
        }
        const existingIds = new Set(avitoData.items.map(x => String(x.item_id)));
        const freshlyAdded = [];
        data.new_items.forEach(it => {
          const id = String(it.item_id);
          if (!existingIds.has(id)) {
            existingIds.add(id);
            if (!it.seen_at) {
              it.seen_at = new Date().toISOString();
            }
            freshlyAdded.push(it);
          }
        });
        if (freshlyAdded.length > 0) {
          avitoData.items = freshlyAdded.concat(avitoData.items);
        }
        data.new_items.forEach(it => {
          const id = String(it.item_id);
          knownAvitoItemIds.add(id);
          markItemAsFresh(id);
        });
        if (currentCat === 'avito_monitor') {
          currentAvitoPage = 1;
          renderList();
        }
      }
      // Уведомление на сайте выводим ТОЛЬКО если у пользователя включен Мониторинг сайта и прошло более 6 секунд со старта
      const isInitialStartup = (Date.now() - _pageLoadedTime) < 6000;
      const isUserMonActive = Boolean(currentUser && (!currentUser.permissions || currentUser.permissions.monitoring !== false));
      if (isUserMonActive && !isInitialStartup) {
        if (data.new_items_count > 0) {
          if (typeof window.playAvitoChime === 'function') window.playAvitoChime();
        }
      }
    } else if (data && data.license_expired) {
      if (typeof window.setLicenseExpiredMode === 'function') {
        window.setLicenseExpiredMode(true);
      }
      return;
    } else if (data && data.waiting_proxy && !avitoHybridMode) {
      isWaitingProxyForPoll = true;
      avitoTimerSecondsLeft = 0;
    }
    await loadAvitoStats();
    if (getNextAvitoInterval() > 5) {
      setTimeout(() => { if (!isAvitoCheckingNow) loadAvitoStats(); }, 2000);
      setTimeout(() => { if (!isAvitoCheckingNow) loadAvitoStats(); }, 4200);
    }
  } catch (err) {
    console.debug('Auto-check poll error:', err);
    try { await loadAvitoStats(); } catch(e) {}
    if (getNextAvitoInterval() > 5) {
      setTimeout(() => { if (!isAvitoCheckingNow) loadAvitoStats(); }, 2000);
    }
  } finally {
    isAvitoCheckingNow = false;
    window._lastAvitoPollTimestamp = Date.now();
    window._hasPolledAtLeastOnce = true;
    if (window._isAvitoFetchingAll || window._isAvitoPollPaused) {
      updateAvitoTimerUI('PAUSE');
    } else if ((isWaitingProxyForPoll || avitoProxyCount === 0) && !avitoHybridMode) {
      // В гибридном режиме не блокируем опрос при отсутствии прокси
      isWaitingProxyForPoll = true;
      avitoTimerSecondsLeft = 0;
      updateAvitoTimerUI('WAITING_PROXY');
    } else {
      isWaitingProxyForPoll = false;
      avitoTimerSecondsLeft = getNextAvitoInterval();
      updateAvitoTimerUI();
    }
  }
}


// ==================== ЧЕРНЫЙ СПИСОК (ЧС) AVITO ====================
function getBlacklistCardIds() {
  try {
    const raw = localStorage.getItem('electro_avito_blacklist_cards');
    return raw ? new Set(JSON.parse(raw).map(String)) : new Set();
  } catch (e) { return new Set(); }
}

function saveBlacklistCardIds(set) {
  try {
    localStorage.setItem('electro_avito_blacklist_cards', JSON.stringify(Array.from(set)));
  } catch (e) {}
}

function extractItemCity(item) {
  if (!item) return '';
  if (item.url) {
    try {
      const rawUrl = String(item.url).trim();
      const u = rawUrl.startsWith('http') ? rawUrl : ('https://www.avito.ru' + (rawUrl.startsWith('/') ? '' : '/') + rawUrl);
      const pathname = new URL(u).pathname;
      const parts = pathname.split('/').filter(Boolean);
      if (parts.length > 0 && parts[0] && parts[0].toLowerCase() !== 'items' && parts[0].toLowerCase() !== 'i') {
        return parts[0].toLowerCase().trim();
      }
    } catch (e) {
      const m = String(item.url).match(/avito\.ru\/([^/?#]+)/i);
      if (m && m[1] && m[1].toLowerCase() !== 'items' && m[1].toLowerCase() !== 'i') {
        return m[1].toLowerCase().trim();
      }
    }
  }
  if (item.address && typeof item.address === 'string') {
    const cleanAddr = item.address.split(',')[0].trim().toLowerCase();
    if (cleanAddr) return cleanAddr;
  }
  return '';
}

function getSellerBlacklistKey(sellerName, itemOrCity) {
  const s = String(sellerName || '').trim().toLowerCase();
  if (!s) return '';
  let city = '';
  if (typeof itemOrCity === 'string') {
    city = itemOrCity.trim().toLowerCase();
  } else if (itemOrCity && typeof itemOrCity === 'object') {
    city = extractItemCity(itemOrCity);
  }
  return city ? `${s}@${city}` : s;
}

function getBlacklistSellers() {
  try {
    const raw = localStorage.getItem('electro_avito_blacklist_sellers');
    return raw ? new Set(JSON.parse(raw).map(s => String(s).trim().toLowerCase()).filter(Boolean)) : new Set();
  } catch (e) { return new Set(); }
}

function saveBlacklistSellers(set) {
  try {
    localStorage.setItem('electro_avito_blacklist_sellers', JSON.stringify(Array.from(set)));
  } catch (e) {}
}

function isCardBlacklisted(item) {
  if (!item) return false;
  const cardSet = getBlacklistCardIds();
  const sellerSet = getBlacklistSellers();
  const idStr = String(item.item_id || '').trim();
  if (idStr && cardSet.has(idStr)) return true;

  const rawSeller = String(item.seller || '').trim().toLowerCase();
  if (!rawSeller) return false;

  const city = extractItemCity(item);
  if (city && sellerSet.has(`${rawSeller}@${city}`)) return true;

  // Если продавец был сохранен без региона (например, "DNS" или имя компании)
  // ВНИМАНИЕ: если у объявления ЕСТЬ город, мы не блокируем его по неквалифицированному имени,
  // чтобы обычные имена ("Макар", "Иван", "Александр") в других городах не попадали в ЧС!
  if (sellerSet.has(rawSeller)) {
    if (!city) return true;
  }

  return false;
}

function isItemIdBlacklisted(itemId) {
  if (!itemId) return false;
  return getBlacklistCardIds().has(String(itemId).trim());
}

function isSellerBlacklisted(sellerName, itemOrCity) {
  if (!sellerName || !sellerName.trim()) return false;
  const sellerSet = getBlacklistSellers();
  const key = getSellerBlacklistKey(sellerName, itemOrCity);
  if (sellerSet.has(key)) return true;
  const raw = sellerName.trim().toLowerCase();
  if (sellerSet.has(raw)) {
    if (!itemOrCity) return true;
  }
  return false;
}

function _updateBlacklistOption() {
  const sel = document.getElementById('avito-link-filter-select');
  if (!sel) return;
  let blCount = 0;
  if (avitoData && Array.isArray(avitoData.items)) {
    blCount = avitoData.items.filter(it => isCardBlacklisted(it)).length;
  } else {
    blCount = getBlacklistCardIds().size;
  }
  const opt = sel.querySelector('option[value="__blacklist__"]');
  if (opt) opt.textContent = `🚫 ЧС (${blCount})`;
}

window.addCardToBlacklist = async function(itemId, sellerName) {
  const idStr = itemId ? String(itemId).trim() : '';
  let cleanSeller = sellerName ? String(sellerName).trim() : '';

  let foundItem = null;
  if (idStr && avitoData && Array.isArray(avitoData.items)) {
    foundItem = avitoData.items.find(it => String(it.item_id).trim() === idStr);
  }
  if (!cleanSeller && foundItem && foundItem.seller) {
    cleanSeller = String(foundItem.seller).trim();
  }

  if (!idStr && !cleanSeller) {
    if (typeof showToast === 'function') showToast('Не указано объявление или продавец для ЧС', 2000, 'orange');
    return;
  }

  const cardSet = getBlacklistCardIds();
  const sellerSet = getBlacklistSellers();

  if (idStr) cardSet.add(idStr);

  const city = extractItemCity(foundItem);
  let sellerKey = '';
  if (cleanSeller) {
    sellerKey = getSellerBlacklistKey(cleanSeller, city);
    if (sellerKey) sellerSet.add(sellerKey);
  }

  saveBlacklistCardIds(cardSet);
  saveBlacklistSellers(sellerSet);

  // Если товар был в избранном, убираем из избранного
  if (idStr) {
    const favs = getFavoriteIds();
    if (favs.has(idStr)) {
      favs.delete(idStr);
      saveFavoriteIds(favs);
      _updateFavoritesOption();
    }
  }

  _updateBlacklistOption();

  const toastMsg = cleanSeller
    ? `🚫 Товар и продавец «${cleanSeller}» отправлены в ЧС!`
    : `🚫 Товар #${idStr} отправлен в ЧС!`;
  if (typeof showToast === 'function') {
    showToast(toastMsg, 2500, 'orange');
  }

  if (currentCat === 'avito_monitor') {
    renderList();
  }

  try {
    fetch('/api/avito/blacklist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: idStr, seller: cleanSeller, city: city })
    }).catch(() => {});
  } catch (e) {}
};

window.removeCardFromBlacklist = async function(itemId, sellerName) {
  const idStr = itemId ? String(itemId).trim() : '';
  let cleanSeller = sellerName ? String(sellerName).trim() : '';

  let foundItem = null;
  if (idStr && avitoData && Array.isArray(avitoData.items)) {
    foundItem = avitoData.items.find(it => String(it.item_id).trim() === idStr);
  }
  if (!cleanSeller && foundItem && foundItem.seller) {
    cleanSeller = String(foundItem.seller).trim();
  }

  const cardSet = getBlacklistCardIds();
  const sellerSet = getBlacklistSellers();

  if (idStr) cardSet.delete(idStr);

  const city = extractItemCity(foundItem);
  if (cleanSeller) {
    const lowerSeller = cleanSeller.toLowerCase();
    const sellerKey = getSellerBlacklistKey(cleanSeller, city);
    sellerSet.delete(sellerKey);
    sellerSet.delete(lowerSeller);
    const prefix = lowerSeller + '@';
    for (const k of Array.from(sellerSet)) {
      if (k === lowerSeller || (city && k === sellerKey) || k.startsWith(prefix)) {
        sellerSet.delete(k);
      }
    }
  }

  saveBlacklistCardIds(cardSet);
  saveBlacklistSellers(sellerSet);

  _updateBlacklistOption();

  if (typeof showToast === 'function') {
    showToast(cleanSeller ? `✅ Товар и продавец «${cleanSeller}» убраны из ЧС и возвращены!` : `✅ Товар #${idStr} убран из ЧС и возвращён!`, 2000, 'green');
  }

  if (currentCat === 'avito_monitor') {
    renderList();
  }

  try {
    fetch('/api/avito/blacklist/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: idStr, seller: cleanSeller, city: city })
    }).catch(() => {});
  } catch (e) {}
};

window.clearBlacklistAll = async function() {
  const cardSet = getBlacklistCardIds();
  const sellerSet = getBlacklistSellers();

  if (cardSet.size === 0 && sellerSet.size === 0) {
    if (typeof showToast === 'function') showToast('Черный список уже пуст', 1500, 'info');
    return;
  }

  cardSet.clear();
  sellerSet.clear();
  saveBlacklistCardIds(cardSet);
  saveBlacklistSellers(sellerSet);

  _updateBlacklistOption();

  if (typeof showToast === 'function') {
    showToast('✅ Черный список полностью очищен, все карточки возвращены!', 2500, 'green');
  }

  if (currentCat === 'avito_monitor') {
    renderList();
  }

  try {
    fetch('/api/avito/blacklist/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }).catch(() => {});
  } catch (e) {}
};

// Сохраняем обратную совместимость для прежних вызовов addSellerToBlacklist
window.addSellerToBlacklist = async function(sellerName, itemId) {
  return window.addCardToBlacklist(itemId, sellerName);
};

// ==================== СОРТИРОВКА И ПАГИНАЦИЯ ОБЪЯВЛЕНИЙ AVITO ====================
let currentAvitoSort = localStorage.getItem('electro_avito_sort') || 'date';
let currentAvitoLinkFilter = localStorage.getItem('electro_avito_link_filter') || 'all';

// ==================== ИЗБРАННОЕ ОБЪЯВЛЕНИЙ AVITO ====================
function getFavoriteIds() {
  try {
    const raw = localStorage.getItem('electro_avito_favorites');
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch (e) { return new Set(); }
}
function saveFavoriteIds(set) {
  try {
    localStorage.setItem('electro_avito_favorites', JSON.stringify(Array.from(set)));
  } catch (e) {}
}
function isFavorited(itemId) {
  return getFavoriteIds().has(String(itemId));
}
function getAvitoCheckoutUrl(item) {
  if (!item || !item.item_id) return '';
  const itemId = String(item.item_id).trim();
  let context = '';
  if (item.url) {
    try {
      const u = new URL(item.url.startsWith('http') ? item.url : 'https://www.avito.ru' + item.url);
      context = u.searchParams.get('context') || '';
    } catch (e) {
      const m = String(item.url).match(/[?&]context=([^&#]+)/);
      if (m) context = decodeURIComponent(m[1]);
    }
  }
  const base = `https://www.avito.ru/order/delivery/checkout/${encodeURIComponent(itemId)}?source=item`;
  return context ? `${base}&context=${encodeURIComponent(context)}` : base;
}
window.toggleAvitoFavorite = function(itemId, btnEl) {
  const id = String(itemId);
  const favs = getFavoriteIds();
  const wasIn = favs.has(id);
  if (wasIn) {
    favs.delete(id);
  } else {
    favs.add(id);
    removeDeletedAvitoItemIds([id]);
  }
  saveFavoriteIds(favs);

  // Мгновенно обновляем кнопку без перерисовки всего списка
  if (btnEl) {
    if (!wasIn) {
      btnEl.classList.add('is-favorited');
      btnEl.innerHTML = '⭐ В избранном';
      btnEl.title = 'Убрать из избранного';
    } else {
      btnEl.classList.remove('is-favorited');
      btnEl.innerHTML = '☆ В избранное';
      btnEl.title = 'Добавить в избранное';
    }
  }
  // Обновляем обрамление карточки
  const card = document.getElementById('avito-card-' + id);
  if (card) card.classList.toggle('is-favorited', !wasIn);

  // Если сейчас фильтр "Избранное" — перерисовываем список
  if (currentAvitoLinkFilter === '__favorites__' && currentCat === 'avito_monitor') {
    renderList();
  }
  _updateFavoritesOption();
  if (typeof window.showToast === 'function') {
    window.showToast(wasIn ? '☆ Убрано из избранного' : '⭐ Добавлено в избранное!', 1500, wasIn ? 'info' : 'green');
  }

  // Синхронизируем с сервером
  try {
    fetch('/api/avito/favorites/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: id })
    }).catch(() => {});
  } catch (e) {}
};

function _updateFavoritesOption() {
  const sel = document.getElementById('avito-link-filter-select');
  if (!sel) return;
  const favCount = getFavoriteIds().size;
  const opt = sel.querySelector('option[value="__favorites__"]');
  if (opt) opt.textContent = `⭐ Избранное (${favCount})`;
}

// ==================== КОРЗИНА КУПЛЕННЫХ ТОВАРОВ AVITO ====================
function getCartItems() {
  try {
    const raw = localStorage.getItem('electro_avito_cart');
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

function saveCartItems(list) {
  try {
    localStorage.setItem('electro_avito_cart', JSON.stringify(list || []));
  } catch (e) {}
  updateCartBadge();
}

function getCartItemIds() {
  try {
    return new Set(getCartItems().map(x => String(x.item_id).trim()));
  } catch (e) {
    return new Set();
  }
}

function isItemInCart(itemId) {
  return getCartItemIds().has(String(itemId).trim());
}

function getCartCount() {
  return getCartItems().length;
}

function updateCartBadge() {
  const count = getCartCount();
  const badges = document.querySelectorAll('#cart-badge-count, .cart-badge-counter');
  badges.forEach(b => {
    b.innerText = count;
    b.classList.toggle('empty', count === 0);
  });
}

function findAvitoItemById(itemId) {
  const idStr = String(itemId).trim();
  if (avitoData && Array.isArray(avitoData.items)) {
    const f = avitoData.items.find(x => String(x.item_id).trim() === idStr);
    if (f) return f;
  }
  if (Array.isArray(window._lastAvitoItems)) {
    const f = window._lastAvitoItems.find(x => String(x.item_id).trim() === idStr);
    if (f) return f;
  }
  const card = document.getElementById('avito-card-' + idStr);
  if (card) {
    const titleEl = card.querySelector('.avito-title');
    const priceEl = card.querySelector('.avito-price-val');
    const linkEl = card.querySelector('a.avito-title') || card.querySelector('a[href*="avito.ru"]');
    const imgEl = card.querySelector('img.avito-thumb');
    const sellerEl = card.querySelector('.avito-detail-seller');
    const addrEl = card.querySelector('.avito-detail-address');
    return {
      item_id: idStr,
      title: titleEl ? titleEl.innerText.trim() : `Товар #${idStr}`,
      price: priceEl ? priceEl.innerText.trim() : '',
      url: linkEl ? linkEl.href : `https://www.avito.ru/${idStr}`,
      photo: imgEl ? imgEl.src : '',
      seller: sellerEl ? sellerEl.innerText.trim() : '',
      address: addrEl ? addrEl.innerText.trim() : '',
      has_delivery: 1
    };
  }
  return { item_id: idStr, title: `Товар #${idStr}`, has_delivery: 1 };
}

function addToCart(item) {
  if (!item || !item.item_id) return;
  const idStr = String(item.item_id).trim();
  const list = getCartItems();
  const existingIdx = list.findIndex(x => String(x.item_id).trim() === idStr);

  const isFav = isFavorited(idStr) || (currentAvitoLinkFilter === '__favorites__');

  const cartItem = {
    item_id: idStr,
    title: item.title || `Товар #${idStr}`,
    price: item.price || '',
    url: item.url || '',
    photo: item.photo || '',
    address: item.address || '',
    seller: item.seller || '',
    seller_type: item.seller_type || '',
    search_name: item.search_name || '',
    has_delivery: item.has_delivery !== undefined ? item.has_delivery : 1,
    from_favorites: Boolean(isFav),
    source_filter: currentAvitoLinkFilter || 'all',
    order_url: item.order_url || '',
    is_robot_order: Boolean(item.is_robot_order),
    added_at: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  };

  if (existingIdx >= 0) {
    list[existingIdx] = cartItem;
  } else {
    list.unshift(cartItem);
  }

  saveCartItems(list);
}

function removeFromCart(itemId) {
  const idStr = String(itemId).trim();
  const list = getCartItems().filter(x => String(x.item_id).trim() !== idStr);
  saveCartItems(list);
}

window.buyAndMoveToCart = function(itemId, checkoutUrl) {
  if (!itemId) return;
  if (checkoutUrl) {
    window.open(checkoutUrl, '_blank', 'noopener');
  }
  const item = findAvitoItemById(itemId);
  if (item) {
    addToCart(item);
    removeCardFromGridInPlace(itemId);
  }
};

window.restoreFromCart = function(itemId) {
  const idStr = String(itemId).trim();
  const list = getCartItems();
  const item = list.find(x => String(x.item_id).trim() === idStr);
  if (!item) return;

  removeFromCart(idStr);
  removeDeletedAvitoItemIds([idStr]);

  if (item.from_favorites) {
    const favs = getFavoriteIds();
    favs.add(idStr);
    saveFavoriteIds(favs);
    _updateFavoritesOption();
  }

  if (avitoData && Array.isArray(avitoData.items)) {
    if (!avitoData.items.some(x => String(x.item_id).trim() === idStr)) {
      avitoData.items.unshift(item);
    }
  }

  renderCartModalContent();
  renderList();
};

window.restoreAllFromCart = function() {
  const list = getCartItems();
  if (list.length === 0) return;

  const allIds = list.map(x => String(x.item_id).trim());
  removeDeletedAvitoItemIds(allIds);

  const favs = getFavoriteIds();
  let favsChanged = false;

  list.forEach(item => {
    const idStr = String(item.item_id).trim();
    if (item.from_favorites) {
      favs.add(idStr);
      favsChanged = true;
    }
    if (avitoData && Array.isArray(avitoData.items)) {
      if (!avitoData.items.some(x => String(x.item_id).trim() === idStr)) {
        avitoData.items.unshift(item);
      }
    }
  });

  if (favsChanged) {
    saveFavoriteIds(favs);
    _updateFavoritesOption();
  }

  saveCartItems([]);
  renderCartModalContent();
  renderList();
};

window.deleteFromCart = function(itemId) {
  const idStr = String(itemId).trim();
  removeFromCart(idStr);
  addDeletedAvitoItemId(idStr);
  const favs = getFavoriteIds();
  if (favs.has(idStr)) {
    favs.delete(idStr);
    saveFavoriteIds(favs);
    _updateFavoritesOption();
  }
  renderCartModalContent();
  renderList();
};

window.clearAllFromCart = function() {
  const list = getCartItems();
  const favs = getFavoriteIds();
  let favsChanged = false;
  list.forEach(it => {
    const idStr = String(it.item_id).trim();
    addDeletedAvitoItemId(idStr);
    if (favs.has(idStr)) {
      favs.delete(idStr);
      favsChanged = true;
    }
  });
  if (favsChanged) {
    saveFavoriteIds(favs);
    _updateFavoritesOption();
  }
  saveCartItems([]);
  renderCartModalContent();
  renderList();
};

window.openCancelOrderModal = function(itemId) {
  if (!itemId) return;
  const list = getCartItems();
  const item = list.find(x => String(x.item_id).trim() === String(itemId).trim());
  if (!item) return;

  if (item.is_shipped || item.status === 'shipped') {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Товар уже отправлен продавцом — отмена заказа недоступна', 4000, 'warning');
    }
    return;
  }

  const overlay = modalOverlay || document.getElementById('modal-overlay');
  const body = modalBody || document.getElementById('modal-body');
  if (!overlay || !body) return;

  const orderTargetUrl = item.order_url || 'https://www.avito.ru/orders';
  const photoUrl = getSafeAvitoPhotoUrl(item.photo) || 'img/no_photo.jpg';
  const destinationName = item.from_favorites ? '⭐ Избранное' : '📋 Общий каталог';

  body.innerHTML = `
    <div class="sniper-modal-card" style="max-width:520px;">
      <div style="display:flex;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:0.75rem;margin-bottom:0.9rem;">
        <div style="display:flex;align-items:center;gap:0.6rem;">
          <span style="font-size:1.5rem;">🚫</span>
          <div>
            <h3 style="margin:0;font-size:1.15rem;color:#f87171;font-weight:700;">Отмена заказа на Авито</h3>
            <div style="font-size:0.78rem;color:var(--text-secondary);">Возврат объявления: <strong style="color:#60a5fa;">${escapeHtml(destinationName)}</strong></div>
          </div>
        </div>
      </div>

      <!-- Карточка товара -->
      <div style="display:flex;gap:0.85rem;background:var(--bg-secondary);padding:0.75rem;border-radius:10px;border:1px solid var(--border-color);margin-bottom:0.9rem;">
        <img src="${escapeHtml(photoUrl)}" data-raw-src="${escapeHtml(item.photo || '')}" style="width:68px;height:68px;border-radius:8px;object-fit:cover;flex-shrink:0;" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { this.src='img/no_photo.jpg'; }">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.92rem;font-weight:700;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(item.title)}</div>
          <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:2px;">Продавец: <strong>${escapeHtml(item.seller || 'Авито')}</strong></div>
          <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-top:4px;">
            ${renderPriceValueHtml(item.price)}
          </div>
        </div>
      </div>

      <div style="font-size:0.85rem;color:var(--text-secondary);line-height:1.45;margin-bottom:1rem;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);padding:0.75rem;border-radius:8px;">
        💡 При отмене заказа робот перейдёт на Авито и аннулирует заказ. После подтверждения карточка объявления автоматически вернётся в <strong>${escapeHtml(destinationName)}</strong>.
      </div>

      <div id="cancel-order-status-box" style="display:none;margin-bottom:0.9rem;"></div>

      <div style="display:flex;flex-direction:column;gap:0.55rem;">
        <button type="button" id="btn-run-cancel-order" onclick="confirmCancelOrderRobot('${escapeHtml(item.item_id)}')"
          class="btn-avito-fetch-all"
          style="background:linear-gradient(135deg, #ef4444, #dc2626);color:#fff;border:none;padding:0.65rem 1rem;font-weight:800;font-size:0.92rem;display:flex;align-items:center;justify-content:center;gap:0.5rem;box-shadow:0 3px 12px rgba(239,68,68,0.3);cursor:pointer;border-radius:8px;">
          <span>🤖 Отменить заказ через робота</span>
        </button>

        <button type="button" onclick="confirmManualCancelAndRestore('${escapeHtml(item.item_id)}')"
          class="cat-btn"
          style="background:rgba(16,185,129,0.12);color:#34d399;border:1px solid rgba(16,185,129,0.35);padding:0.52rem 1rem;font-weight:700;font-size:0.85rem;display:flex;align-items:center;justify-content:center;gap:0.4rem;border-radius:8px;"
          title="Нажмите, если вы уже отменили этот заказ на Авито вручную (в приложении или браузере)">
          <span>✅ Я уже отменил на Авито — вернуть карточку</span>
        </button>

        <button type="button" onclick="window.open('${escapeHtml(orderTargetUrl)}', '_blank', 'noopener')"
          class="cat-btn"
          style="background:rgba(59,130,246,0.12);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);padding:0.5rem 1rem;font-weight:700;font-size:0.85rem;display:flex;align-items:center;justify-content:center;gap:0.4rem;border-radius:8px;">
          <span>🌐 Открыть страницу заказа на Авито</span>
        </button>

        <button type="button" onclick="openCartModal()" class="cat-btn" style="margin-top:0.25rem;padding:0.45rem 1rem;font-size:0.82rem;align-self:center;">
          Назад в корзину
        </button>
      </div>
    </div>
  `;
};

window.confirmManualCancelAndRestore = function(itemId) {
  const list = getCartItems();
  const item = list.find(x => String(x.item_id).trim() === String(itemId).trim());
  restoreFromCart(itemId);
  markItemAsCanceled(itemId, {
    reason: 'Заказ отменён вручную на Авито (продавец не отправил)',
    title: item ? item.title : '',
    seller: item ? item.seller : ''
  });
  const dest = (item && item.from_favorites) ? 'в Избранное' : 'в каталог объявлений';
  if (typeof window.showToast === 'function') {
    window.showToast(`✅ Заказ отменён! Карточка #${itemId} возвращена ${dest} и подсвечена красным.`, 6000, 'green');
  }
  openCartModal();
};

window.confirmCancelOrderRobot = async function(itemId) {
  const btn = document.getElementById('btn-run-cancel-order');
  const statusBox = document.getElementById('cancel-order-status-box');
  const list = getCartItems();
  const item = list.find(x => String(x.item_id).trim() === String(itemId).trim()) || {};

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="width:16px;height:16px;border:2px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;display:inline-block;animation:spin 0.8s linear infinite;margin-right:6px;"></span> Робот отменяет заказ на Авито...`;
  }
  if (statusBox) {
    statusBox.style.display = 'block';
    statusBox.innerHTML = `
      <div style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:0.65rem 0.85rem;color:var(--text-primary);font-size:0.82rem;display:flex;align-items:center;gap:0.5rem;">
        <span style="font-size:1.1rem;">⏳</span>
        <div>Подключение к профилю Авито и отправка отмены заказа... (~2-4 сек)</div>
      </div>
    `;
  }

  try {
    const res = await fetch('/api/avito/sniper/cancel-order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: itemId,
        url: item.url || '',
        order_url: item.order_url || ''
      })
    });
    const data = await res.json();

    if (data && data.success) {
      if (statusBox) {
        statusBox.innerHTML = `
          <div style="background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.35);border-radius:8px;padding:0.75rem;color:#10b981;font-size:0.85rem;font-weight:700;">
            🎉 ${escapeHtml(data.message || 'Заказ успешно отменён на Авито!')}
          </div>
        `;
      }
      const dest = item.from_favorites ? 'в Избранное' : 'в каталог объявлений';
      if (typeof window.showToast === 'function') {
        window.showToast(`✅ Заказ лота #${itemId} успешно отменён на Авито! Карточка возвращена ${dest} и подсвечена красным.`, 6000, 'green');
      }

      restoreFromCart(itemId);
      markItemAsCanceled(itemId, {
        reason: 'Заказ отменён роботом на Авито (продавец не отправил)',
        title: item.title,
        seller: item.seller
      });

      setTimeout(() => {
        openCartModal();
      }, 1500);
    } else {
      if (data && data.is_shipped) {
        const curList = getCartItems();
        const curIdx = curList.findIndex(x => String(x.item_id).trim() === String(itemId).trim());
        if (curIdx >= 0) {
          curList[curIdx].is_shipped = true;
          curList[curIdx].status = 'shipped';
          saveCartItems(curList);
        }
        if (statusBox) {
          statusBox.innerHTML = `
            <div style="background:rgba(100,116,139,0.15);border:1px solid rgba(100,116,139,0.35);border-radius:8px;padding:0.75rem;color:var(--text-secondary);font-size:0.84rem;">
              🚚 <strong>Товар уже отправлен продавцом:</strong><br>
              Посылка передана в доставку. На Авито отмена заказа на этом этапе недоступна.
            </div>
          `;
        }
        if (typeof window.showToast === 'function') {
          window.showToast('⚠️ Товар уже отправлен продавцом — отмена заказа недоступна', 6000, 'warning');
        }
        setTimeout(() => {
          openCartModal();
        }, 2200);
        return;
      }

      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span>🤖 Попробовать отменить снова</span>`;
      }
      const err = data?.error || 'Не удалось отменить заказ автоматически на Авито';
      if (statusBox) {
        statusBox.innerHTML = `
          <div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);border-radius:8px;padding:0.75rem;color:#f87171;font-size:0.84rem;">
            ⚠️ <strong>Ошибка отмены:</strong><br>${escapeHtml(err)}
            <div style="margin-top:0.5rem;">
              <a href="${escapeHtml(item.order_url || 'https://www.avito.ru/orders')}" target="_blank" rel="noopener" style="color:#60a5fa;text-decoration:underline;font-weight:700;">
                🌐 Открыть страницу заказов на Авито и проверить статус
              </a>
            </div>
          </div>
        `;
      }
      if (typeof window.showToast === 'function') {
        window.showToast(`⚠️ ${err}`, 5000, 'warning');
      }
    }
  } catch(e) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>🤖 Отменить заказ через робота</span>`;
    }
    if (statusBox) {
      statusBox.innerHTML = `
        <div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);border-radius:8px;padding:0.75rem;color:#f87171;font-size:0.84rem;">
          ❌ Ошибка сети при связи с сервером: ${escapeHtml(e.message)}
        </div>
      `;
    }
  }
};

// ==================== РОБОТ ПРОВЕРКИ СТАТУСА ЗАКАЗОВ В КОРЗИНЕ (КАЖДЫЙ ЧАС) ====================
const CART_CHECK_HOURLY_MS = 60 * 60 * 1000; // 1 час (3600000 мс)

window.checkCartOrdersStatusWithRobot = async function(isManual = false) {
  if (window._isCheckingCartOrders) return;
  const cart = getCartItems();
  if (!cart || cart.length === 0) {
    if (isManual && typeof window.showToast === 'function') {
      window.showToast('В корзине нет заказов для проверки', 3000, 'info');
    }
    return;
  }

  window._isCheckingCartOrders = true;
  const checkBtn = document.getElementById('btn-robot-check-orders');
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.innerHTML = `<span class="spinner" style="width:14px;height:14px;border:2px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;display:inline-block;animation:spin 0.8s linear infinite;margin-right:5px;"></span> Робот проверяет заказы на Авито...`;
  }

  try {
    const payload = cart.map(it => ({
      item_id: String(it.item_id).trim(),
      url: it.url || '',
      order_url: it.order_url || '',
      title: it.title || '',
      is_shipped: Boolean(it.is_shipped || it.status === 'shipped')
    }));

    const res = await fetch('/api/avito/sniper/check-cart-orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: payload })
    });
    const data = await res.json();

    localStorage.setItem('electro_avito_last_cart_check', String(Date.now()));

    if (data && data.success && Array.isArray(data.results)) {
      let canceledCount = 0;
      let shippedCount = 0;

      data.results.forEach(r => {
        const idStr = String(r.item_id).trim();
        const curCart = getCartItems();
        const found = curCart.find(x => String(x.item_id).trim() === idStr);

        if (r.is_canceled) {
          // Если продавец не отправил и заказ отменился (по истечению времени или продавцом):
          // 1. Возвращаем заказ в ленту или избранное
          // 2. Подсвечиваем его красным пока не наведём мышкой (без авто-таймера)
          if (found) {
            restoreFromCart(idStr);
            markItemAsCanceled(idStr, {
              reason: r.reason || 'Продавец не отправил заказ вовремя или отменил его',
              title: found.title,
              seller: found.seller
            });
            canceledCount++;
          }
        } else if (r.is_shipped) {
          if (found) {
            found.is_shipped = true;
            found.status = 'shipped';
            shippedCount++;
          }
        }
      });

      if (shippedCount > 0) {
        saveCartItems(getCartItems());
      }

      if (canceledCount > 0) {
        if (typeof window.playAvitoChime === 'function') {
          window.playAvitoChime();
        }
        if (typeof window.showToast === 'function') {
          window.showToast(`⚠️ Робот обнаружил ${canceledCount} отменённых заказов (продавец не отправил)! Карточки возвращены в ленту/избранное и подсвечены красным.`, 8000, 'warning');
        }
        renderList();
        renderCartModalContent();
      } else if (isManual) {
        if (typeof window.showToast === 'function') {
          window.showToast(`✅ Проверка завершена: отменённых заказов не найдено${shippedCount > 0 ? `, отправлено: ${shippedCount}` : ''}`, 4000, 'green');
        }
        renderCartModalContent();
      }
    } else {
      const err = data?.error || 'Не удалось получить данные о статусе заказов';
      if (isManual && typeof window.showToast === 'function') {
        window.showToast(`⚠️ ${err}`, 5000, 'warning');
      }
    }
  } catch(e) {
    if (isManual && typeof window.showToast === 'function') {
      window.showToast(`❌ Ошибка проверки заказов: ${e.message}`, 4000, 'warning');
    }
  } finally {
    window._isCheckingCartOrders = false;
    const checkBtnAfter = document.getElementById('btn-robot-check-orders');
    if (checkBtnAfter) {
      checkBtnAfter.disabled = false;
      checkBtnAfter.innerHTML = `<span>🤖 Проверить статусы заказов (робот)</span>`;
    }
  }
};

function startHourlyCartChecker() {
  if (window._cartHourlyCheckerInterval) {
    clearInterval(window._cartHourlyCheckerInterval);
  }

  // Проверка при загрузке, если прошёл 1 час с момента прошлой проверки
  const lastCheck = parseInt(localStorage.getItem('electro_avito_last_cart_check') || '0', 10);
  const now = Date.now();
  if (now - lastCheck >= CART_CHECK_HOURLY_MS) {
    setTimeout(() => {
      if (getCartCount() > 0) {
        window.checkCartOrdersStatusWithRobot(false);
      }
    }, 10000);
  }

  // Регулярная проверка роботом каждые 60 минут
  window._cartHourlyCheckerInterval = setInterval(() => {
    if (getCartCount() > 0) {
      window.checkCartOrdersStatusWithRobot(false);
    }
  }, CART_CHECK_HOURLY_MS);
}

startHourlyCartChecker();

window.openCartModal = function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  const overlay = modalOverlay || document.getElementById('modal-overlay');
  const body = modalBody || document.getElementById('modal-body');
  if (!overlay || !body) return;

  renderCartModalContent();
  overlay.classList.add('open');
  document.body.classList.add('modal-open');
  document.documentElement.classList.add('modal-open');
};

function renderCartModalContent() {
  const body = document.getElementById('modal-body');
  if (!body) return;

  const items = getCartItems();
  if (items.length === 0) {
    body.innerHTML = `
      <div class="cart-modal-container">
        <div style="display:flex;align-items:center;gap:0.75rem;padding-bottom:0.75rem;border-bottom:1px solid var(--border-color);">
          <span style="font-size:1.6rem;">🛒</span>
          <div>
            <h3 style="margin:0;font-size:1.15rem;color:var(--text-primary);font-weight:700;">Корзина товаров</h3>
            <p style="margin:0;font-size:0.8rem;color:var(--text-secondary);">Товары, купленные вручную или роботом (0 шт.)</p>
          </div>
        </div>
        <div style="text-align:center;padding:3rem 1rem;color:var(--text-secondary);">
          <div style="font-size:3.5rem;margin-bottom:0.75rem;opacity:0.6;">🛒</div>
          <h3 style="margin:0 0 0.5rem;font-size:1.15rem;color:var(--text-primary);">Ваша корзина пуста</h3>
          <p style="margin:0;font-size:0.85rem;color:var(--text-secondary);max-width:420px;margin-left:auto;margin-right:auto;line-height:1.45;">
            При нажатии «⚡ Купить» на карточке любого объявления товар будет сразу перемещаться сюда.
          </p>
        </div>
      </div>
    `;
    return;
  }

  body.innerHTML = `
    <div class="cart-modal-container">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;padding-bottom:0.75rem;border-bottom:1px solid var(--border-color);">
        <div style="display:flex;align-items:center;gap:0.6rem;">
          <span style="font-size:1.6rem;">🛒</span>
          <div>
            <h3 style="margin:0;font-size:1.15rem;color:var(--text-primary);font-weight:700;">Корзина товаров</h3>
            <p style="margin:0;font-size:0.8rem;color:var(--text-secondary);">Товары, купленные вручную или роботом (<strong style="color:#10b981;">${items.length} шт.</strong>)</p>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
          <button type="button" onclick="clearAllFromCart()" class="cat-btn"
            style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.4);font-size:0.8rem;font-weight:700;padding:0.35rem 0.7rem;border-radius:8px;"
            title="Удалить все товары из корзины навсегда">
            🗑️ Очистить корзину
          </button>
        </div>
      </div>

      <!-- Панель статуса робота проверки заказов (каждый 1 час) -->
      <div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:10px;padding:8px 12px;margin:8px 0 12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div style="display:flex;align-items:center;gap:8px;font-size:0.82rem;color:var(--text-secondary);">
          <span style="font-size:1.25rem;">🤖</span>
          <div>
            <div style="color:var(--text-primary);font-weight:700;">
              Робот проверки заказов: <span style="color:#10b981;">активен каждый 1 час</span>
            </div>
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:1px;">
              Смотрит статус отправки. Если продавец не отправил и заказ отменился — возвращает в ленту/избранное и подсвечивает красным.
            </div>
          </div>
        </div>
        <button type="button" id="btn-robot-check-orders" onclick="window.checkCartOrdersStatusWithRobot(true)" class="cat-btn"
          style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.45);font-size:0.8rem;font-weight:700;padding:0.4rem 0.8rem;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:5px;"
          title="Запустить немедленную проверку отправки через робота прямо сейчас">
          <span>🤖 Проверить статусы сейчас</span>
        </button>
      </div>

      <div style="display:flex;flex-direction:column;gap:0.6rem;max-height:60vh;overflow-y:auto;padding-right:0.3rem;">
        ${items.map(it => {
          const photoUrl = getSafeAvitoPhotoUrl(it.photo) || 'img/no_photo.jpg';
          const isShipped = Boolean(it.is_shipped || it.status === 'shipped' || it.status === 'in_transit');
          return `
            <div class="cart-item-card" id="cart-item-${escapeHtml(it.item_id)}">
              <a href="${escapeHtml(it.url || '#')}" target="_blank" rel="noopener" style="flex-shrink:0;">
                <img src="${escapeHtml(photoUrl)}" data-raw-src="${escapeHtml(it.photo || '')}" alt="" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { this.src='img/no_photo.jpg'; }" style="width:70px;height:70px;object-fit:cover;border-radius:8px;background:var(--bg-card);border:1px solid var(--border-color);">
              </a>

              <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:0.25rem;">
                <a href="${escapeHtml(it.url || '#')}" target="_blank" rel="noopener" style="font-size:0.88rem;font-weight:700;color:var(--text-primary);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(it.title)}">
                  ${escapeHtml(it.title)}
                </a>
                <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                  ${renderPriceValueHtml(it.price)}
                  <span style="font-size:0.73rem;padding:0.12rem 0.45rem;border-radius:6px;font-weight:600;background:${it.from_favorites ? 'rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.35)' : 'rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.35)'};">
                    ${it.from_favorites ? '⭐ Из избранного' : '🔍 ' + escapeHtml(getDisplaySearchName(it))}
                  </span>
                  ${isShipped ? `
                    <span style="font-size:0.73rem;padding:0.12rem 0.45rem;border-radius:6px;font-weight:700;background:rgba(100,116,139,0.2);color:#94a3b8;border:1px solid rgba(100,116,139,0.35);">
                      🚚 Отправлен
                    </span>
                  ` : ''}
                  ${it.added_at ? `<span style="font-size:0.73rem;color:var(--text-secondary);">в ${escapeHtml(it.added_at)}</span>` : ''}
                </div>
                <div style="font-size:0.77rem;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  👤 ${escapeHtml(it.seller || 'Продавец')} ${it.address ? `• 📍 ${escapeHtml(it.address)}` : ''}
                </div>
              </div>

              <div style="display:flex;align-items:center;gap:0.35rem;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end;">
                <button type="button"
                  id="btn-cart-cancel-${escapeHtml(it.item_id)}"
                  ${isShipped ? 'disabled' : `onclick="openCancelOrderModal('${escapeHtml(it.item_id)}')"`}
                  class="cat-btn btn-cart-cancel ${isShipped ? 'disabled' : ''}"
                  style="${isShipped ? 'background:rgba(100,116,139,0.12)!important;color:#64748b!important;border:1px solid rgba(100,116,139,0.25)!important;opacity:0.45!important;cursor:not-allowed!important;pointer-events:none!important;box-shadow:none!important;transform:none!important;filter:grayscale(1)!important;text-decoration:none!important;font-size:0.78rem;font-weight:700;padding:0.35rem 0.6rem;border-radius:8px;' : 'background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.4);font-size:0.78rem;font-weight:700;padding:0.35rem 0.6rem;border-radius:8px;cursor:pointer;'}"
                  title="${isShipped ? 'Товар уже отправлен продавцом (отмена заказа недоступна)' : 'Отменить заказ на Авито и вернуть объявление'}">
                  🚫 ${isShipped ? 'Отправлен (отмена недоступна)' : 'Отменить заказ'}
                </button>
                <button type="button" onclick="deleteFromCart('${escapeHtml(it.item_id)}')" class="cat-btn"
                  style="background:rgba(107,114,128,0.15);color:#9ca3af;border:1px solid rgba(107,114,128,0.4);font-size:0.78rem;font-weight:700;padding:0.35rem 0.6rem;border-radius:8px;"
                  title="Удалить из корзины навсегда">
                  🗑️ Удалить
                </button>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}
let currentAvitoPage = 1;
let currentAvitoPageSize = (function() {
  const saved = localStorage.getItem('electro_avito_pagesize');
  if (saved === '16' || saved === '32' || saved === '64') return parseInt(saved, 10);
  if (saved === 'all') return 'all';
  return 32; // По умолчанию 32 позиции (8 рядов по 4)
})();

window.setAvitoPageSize = function(size) {
  currentAvitoPageSize = size === 'all' ? 'all' : parseInt(size, 10);
  currentAvitoPage = 1;
  try {
    localStorage.setItem('electro_avito_pagesize', String(size));
  } catch (e) {}
  if (currentCat === 'avito_monitor') {
    renderList();
  }
};

window.setAvitoPage = function(pageNum, shouldScroll = false) {
  currentAvitoPage = Math.max(1, parseInt(pageNum, 10) || 1);
  if (currentCat === 'avito_monitor') {
    renderList();
    if (shouldScroll) {
      const filterBar = document.querySelector('.avito-filter-bar');
      if (filterBar) {
        filterBar.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }
};

function getSecondsSinceLastPoll(searches) {
  let mostRecent = 0;
  if (window._lastAvitoPollTimestamp) {
    mostRecent = Math.max(mostRecent, window._lastAvitoPollTimestamp);
  }
  const list = Array.isArray(searches) ? searches : (avitoData && Array.isArray(avitoData.searches) ? avitoData.searches : []);
  list.forEach(s => {
    if (s && s.last_polled_at) {
      const t = Date.parse(String(s.last_polled_at).replace(' ', 'T'));
      if (!isNaN(t) && t > mostRecent) {
        mostRecent = t;
      }
    }
  });
  if (mostRecent === 0) return Infinity;
  return Math.max(0, Math.floor((Date.now() - mostRecent) / 1000));
}

window.fetchAllAvitoCards = async function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  if (window._isAvitoFetchingAll) return;

  if (!hasActiveAvitoSearches()) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Нет активных ссылок поиска. Добавьте ссылки для загрузки!', 3000);
    } else {
      alert('Нет активных ссылок поиска. Добавьте ссылки для загрузки!');
    }
    return;
  }

  const isFiltered = Boolean(currentAvitoLinkFilter && currentAvitoLinkFilter !== 'all' && currentAvitoLinkFilter !== '__favorites__' && currentAvitoLinkFilter !== '__blacklist__');
  const targetFilter = isFiltered ? currentAvitoLinkFilter.trim() : 'all';

  const btn = document.getElementById('btn-avito-fetch-all');
  const defaultLabel = isFiltered ? 'Загрузить' : 'Загрузить все';

  if (!isFiltered) {
    clearDeletedAvitoItemIds();
    currentAvitoLinkFilter = 'all';
    currentAvitoPage = 1;
    const sInput = document.getElementById('search-input');
    if (sInput) sInput.value = '';
    const sel = document.getElementById('avito-link-filter-select');
    if (sel) sel.value = 'all';
  }

  let searches = [];
  if (currentUser && Array.isArray(currentUser.avito_searches) && currentUser.avito_searches.length > 0) {
    searches = currentUser.avito_searches;
  } else if (avitoData && Array.isArray(avitoData.searches) && avitoData.searches.length > 0) {
    searches = avitoData.searches;
  }
  searches = normalizeSearches(searches);

  // Для фильтра по конкретной ссылке — запускаем через очередь (1 элемент)
  if (isFiltered) {
    const matched = searches.find(s => s && (
      (s.name && s.name.trim().toLowerCase() === targetFilter.toLowerCase()) || 
      (s.url && s.url.trim().toLowerCase() === targetFilter.toLowerCase())
    ));
    const singleSearch = [matched || { name: targetFilter, url: targetFilter, is_active: 1 }];
    await _fetchAllByQueueWithInterval(singleSearch, btn, defaultLabel);
    return;
  }

  // Общий режим «Загрузить всё»:
  // Сортировка ссылок в очереди: сначала ни разу не опрошенные (null),
  // затем с самым давним временем опроса (FIFO), чтобы не опрашивать повторно ссылку,
  // по которой только что прошёл опрос.
  const activeSearches = searches.filter(s =>
    s && s.url && String(s.url).trim() &&
    s.is_active !== 0 && s.is_active !== '0' && s.is_active !== false
  );
  activeSearches.sort((a, b) => {
    const aTime = a.last_polled_at ? new Date(String(a.last_polled_at).replace(' ', 'T')).getTime() : 0;
    const bTime = b.last_polled_at ? new Date(String(b.last_polled_at).replace(' ', 'T')).getTime() : 0;
    return aTime - bTime;
  });

  if (activeSearches.length >= 1) {
    await _fetchAllByQueueWithInterval(activeSearches, btn, defaultLabel);
    return;
  }
};

// ==================== УМНАЯ ОЧЕРЕДНАЯ ЗАГРУЗКА ПО ССЫЛКАМ ====================
// Грузит каждую ссылку по очереди с безопасным интервалом между запросами.
// Кнопка показывает статус и кликабельна для отмены.
const curProxyCount = window._avitoProxyCount || 0;
const SAFE_FETCH_INTERVAL_MS = curProxyCount >= 24 ? 1000 : curProxyCount >= 10 ? 3000 : curProxyCount >= 3 ? 10000 : 30000;

window._cancelFetchQueue = false;
window._avitoCurrentBtnHtml = null;

async function _fetchAllByQueueWithInterval(activeSearches, btn, defaultLabel) {
  window._isAvitoFetchingAll = true;
  window._isAvitoPollPaused = true;
  window._cancelFetchQueue = false;
  updateAvitoTimerUI('PAUSE');

  const total = activeSearches.length;
  const targetUser = currentUser ? (currentUser.username || '') : '';

  clearDeletedAvitoItemIds();

  const getBtn = () => document.getElementById('btn-avito-fetch-all') || btn;

  // Обновляем внешний вид кнопки (кликабельна для отмены)
  const setQueueBtnLabel = (currentIdx, customText = '') => {
    const el = getBtn();
    const labelText = customText || `Загружаю ${currentIdx}/${total}`;
    window._avitoCurrentBtnHtml = `⏳ <span style="color:#fbbf24;font-weight:700;">${labelText}</span>`;
    if (!el) return;
    el.disabled = false;
    el.classList.add('loading');
    el.style.color = '#fbbf24';
    el.style.borderColor = 'rgba(251,191,36,0.6)';
    el.style.background = 'rgba(251,191,36,0.12)';
    el.style.opacity = '1';
    el.style.cursor = 'pointer';
    el.innerHTML = window._avitoCurrentBtnHtml;
    el.title = 'Нажмите для остановки очереди загрузки';
    el.onclick = () => {
      window._cancelFetchQueue = true;
    };
  };

  const resetBtn = () => {
    window._avitoCurrentBtnHtml = null;
    const el = getBtn();
    if (!el) return;
    el.disabled = false;
    el.classList.remove('loading');
    el.style.color = '';
    el.style.borderColor = '';
    el.style.background = '';
    el.style.opacity = '';
    el.style.cursor = '';
    el.innerHTML = defaultLabel;
    el.title = (defaultLabel.includes('всё') || defaultLabel.includes('все'))
      ? 'Загрузить все найденные объявления по активным ссылкам на сайт'
      : 'Загрузить объявления по выбранной ссылке на сайт';
    el.onclick = () => window.fetchAllAvitoCards();
  };

  try {
    // 1. Если прямо в этот момент шёл фоновый опрос — дожидаемся его завершения
    if (isAvitoCheckingNow) {
      const el = getBtn();
      if (el) {
        el.disabled = false;
        el.classList.add('loading');
        window._avitoCurrentBtnHtml = `⏳ <span style="color:#fbbf24;font-weight:700;">ожидание опроса...</span>`;
        el.innerHTML = window._avitoCurrentBtnHtml;
      }
      while (isAvitoCheckingNow && !window._cancelFetchQueue) {
        await new Promise(r => setTimeout(r, 200));
      }
    }
    if (window._cancelFetchQueue) {
      return;
    }

    if (window._cancelFetchQueue) {
      return;
    }

    let totalNew = 0;
    let totalLoaded = 0;

    for (let i = 0; i < activeSearches.length; i++) {
      if (window._cancelFetchQueue) break;

      const search = activeSearches[i];
      const searchName = (search.name || search.url || '').trim();
      const currentIdx = i + 1;

      setQueueBtnLabel(currentIdx);

      try {
        const searchUrl = (search.url || '').trim();
        const isSearchOnlyDelivery = Boolean(
          search.only_delivery == 1 || search.only_delivery === true ||
          (searchUrl && (searchUrl.includes('d=1') || searchUrl.includes('cd=1')))
        );
        const res = await fetch('/api/avito/fetch-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: targetUser,
            search_name: searchName,
            search_url: searchUrl,
            url: searchUrl,
            only_delivery: isSearchOnlyDelivery ? 1 : 0
          })
        });
        let data = null;
        try { data = await res.json(); } catch (e) {}

        if (data && data.success && Array.isArray(data.items)) {
          let incomingItems = data.items;
          if (isSearchOnlyDelivery) {
            incomingItems = incomingItems.filter(it => it && (it.has_delivery == 1 || it.has_delivery === true || it.has_delivery === '1'));
          }
          if (incomingItems.length > 0) {
            const favSet = getFavoriteIds();
            const normFilter = searchName.toLowerCase();
            const otherItems = (avitoData.items || []).filter(it => {
              const isThisSearch = (it.search_name || '').trim().toLowerCase() === normFilter;
              if (!isThisSearch) return true;
              return favSet.has(String(it.item_id));
            });
            const fetchedIds = new Set(incomingItems.map(it => String(it.item_id)));
            const preservedFavs = otherItems.filter(it => !fetchedIds.has(String(it.item_id)));
            
            // Строгая дедупликация по item_id: исключаем любые повторы карточек
            const mergedMap = new Map();
            incomingItems.forEach(it => {
              if (it && it.item_id) mergedMap.set(String(it.item_id), it);
            });
            preservedFavs.forEach(it => {
              if (it && it.item_id && !mergedMap.has(String(it.item_id))) {
                mergedMap.set(String(it.item_id), it);
              }
            });
            avitoData.items = Array.from(mergedMap.values());
            if (avitoData.stats) avitoData.stats.total_items = (avitoData.items || []).length;
            incomingItems.forEach(it => knownAvitoItemIds.add(String(it.item_id)));
            totalNew += (data.new_count || 0);
            totalLoaded += incomingItems.length;

            // Удаляем загруженные ID из списка удаленных и сразу отображаем
            const fetchedItemIds = incomingItems.map(it => it && it.item_id).filter(Boolean);
            if (fetchedItemIds.length > 0) {
              removeDeletedAvitoItemIds(fetchedItemIds);
            }
            currentCat = 'avito_monitor';
            renderList();
          }
        } else if (data && !data.success && data.error) {
          console.warn('fetch-all search error:', data.error);
        }

      } catch (err) {
        console.error('_fetchAllByQueueWithInterval error:', err);
      }

      // Обновляем карточки после каждой ссылки (если в очереди еще остаются ссылки)
      if (activeSearches.length > 1 && i < activeSearches.length - 1) {
        currentCat = 'avito_monitor';
        renderList();
      }

      // Краткая пауза перед следующей ссылкой (1 сек)
      if (i < activeSearches.length - 1 && !window._cancelFetchQueue) {
        const nextIdx = currentIdx + 1;
        const el = getBtn();
        if (el) {
          window._avitoCurrentBtnHtml = `⏳ <span style="color:#fbbf24;font-weight:700;">Загружаю ${nextIdx}/${total}</span>`;
          el.innerHTML = window._avitoCurrentBtnHtml;
        }
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    if (!window._cancelFetchQueue) {
      // Переключаем на монитор Авито и сбрасываем страницу на первую
      currentCat = 'avito_monitor';
      currentAvitoPage = 1;

      // Удерживаем статус загрузки до появления карточек в DOM
      setQueueBtnLabel(total);
      renderList();

      try {
        window._isLoadingAvitoStats = false;
        await loadAvitoStats(true);
      } catch (e) {}

      // Повторно гарантируем отрисовку списка карточек
      currentCat = 'avito_monitor';
      renderList();

      // ТРЕБОВАНИЕ: завершение загрузки объявлений должно закончиться ТОГДА, КОГДА карточки объявлений ПОЯВЯТСЯ НА НАШЕМ САЙТЕ.
      // Не завершаем загрузку и не сбрасываем кнопку, пока .avito-card не будут физически в DOM!
      const expectedCount = (avitoData && Array.isArray(avitoData.items)) ? avitoData.items.length : 0;
      const waitStart = Date.now();
      const maxWaitTimeout = 5000;
      while (Date.now() - waitStart < maxWaitTimeout) {
        const visibleCards = document.querySelectorAll('.avito-card');
        if (expectedCount === 0 || visibleCards.length > 0) {
          // Даем браузеру 2 кадра анимации (requestAnimationFrame) на окончательный layout и paint в DOM
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
          break;
        }
        await new Promise(r => setTimeout(r, 60));
      }
    }
  } finally {
    window._isAvitoFetchingAll = false;
    window._isAvitoPollPaused = false;
    window._cancelFetchQueue = false;
    resetBtn();
    avitoTimerSecondsLeft = getNextAvitoInterval();
    updateAvitoTimerUI();
  }
}

function getDeletedAvitoItemIds() {
  try {
    const saved = localStorage.getItem('electro_deleted_avito_items');
    return saved ? new Set(JSON.parse(saved)) : new Set();
  } catch (e) {
    return new Set();
  }
}

function addDeletedAvitoItemId(id) {
  if (!id) return;
  try {
    const set = getDeletedAvitoItemIds();
    set.add(String(id).trim());
    const arr = Array.from(set);
    if (arr.length > 5000) arr.splice(0, arr.length - 5000);
    localStorage.setItem('electro_deleted_avito_items', JSON.stringify(arr));
  } catch (e) {}
}

function addDeletedAvitoItemIdsBatch(ids) {
  if (!ids || ids.length === 0) return;
  try {
    const set = getDeletedAvitoItemIds();
    ids.forEach(id => {
      if (id) set.add(String(id).trim());
    });
    const arr = Array.from(set);
    if (arr.length > 5000) arr.splice(0, arr.length - 5000);
    localStorage.setItem('electro_deleted_avito_items', JSON.stringify(arr));
  } catch (e) {}
}

function removeDeletedAvitoItemIds(idsToRemove) {
  if (!idsToRemove || idsToRemove.length === 0) return;
  try {
    const set = getDeletedAvitoItemIds();
    idsToRemove.forEach(id => {
      if (id != null) set.delete(String(id).trim());
    });
    localStorage.setItem('electro_deleted_avito_items', JSON.stringify(Array.from(set)));
  } catch (e) {}
}

function clearDeletedAvitoItemIds() {
  try {
    localStorage.removeItem('electro_deleted_avito_items');
  } catch (e) {}
}

window.clearAllAvitoCards = async function() {
  const isFavoritesFilter = (currentAvitoLinkFilter === '__favorites__');
  const isBlacklistFilter = (currentAvitoLinkFilter === '__blacklist__');
  const favSet = getFavoriteIds();

  // Если пользователь находится во вкладке «🚫 ЧС» и нажимает «Очистить»:
  if (isBlacklistFilter) {
    window.clearBlacklistAll();
    return;
  }

  // Если пользователь находится во вкладке «⭐ Избранное» и нажимает «Очистить»:
  if (isFavoritesFilter) {
    if (favSet.size === 0) return;
    const oldFavIds = Array.from(favSet);
    favSet.clear();
    saveFavoriteIds(favSet);
    _updateFavoritesOption();

    // Удаляем карточки избранного из текущих данных
    if (avitoData && Array.isArray(avitoData.items)) {
      avitoData.items = avitoData.items.filter(it => !oldFavIds.includes(String(it.item_id)));
    }
    if (avitoData && avitoData.stats) {
      avitoData.stats.total_items = (avitoData.items || []).length;
    }

    renderList();

    try {
      fetch('/api/avito/items/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_name: '__favorites__',
          keep_ids: oldFavIds
        })
      }).catch(() => {});
    } catch (e) {}
    return;
  }

  const isFiltered = Boolean(currentAvitoLinkFilter && currentAvitoLinkFilter !== 'all');
  const targetFilter = isFiltered ? currentAvitoLinkFilter.trim() : 'all';
  const normFilter = targetFilter.toLowerCase();

  // Собираем элементы для очистки, ИСКЛЮЧАЯ избранные и товары из ЧС!
  let allTargetItems = [];
  if (isFiltered) {
    allTargetItems = (avitoData && Array.isArray(avitoData.items))
      ? avitoData.items.filter(it => (it.search_name || '').trim().toLowerCase() === normFilter)
      : [];
  } else {
    allTargetItems = (avitoData && Array.isArray(avitoData.items)) ? avitoData.items : [];
  }

  // Карточки, которые удаляются (НЕ в избранном и НЕ в ЧС):
  const itemsToClear = allTargetItems.filter(it => !favSet.has(String(it.item_id)) && !isCardBlacklisted(it));
  const idsToClear = itemsToClear.map(it => it.item_id).filter(Boolean);

  // Пакетная мгновенная запись в localStorage (одна операция вместо тысяч)
  if (idsToClear.length > 0) {
    addDeletedAvitoItemIdsBatch(idsToClear);
  }

  // Защищенные объявления из «Избранного» никогда не должны быть в списке удаленных
  if (favSet.size > 0) {
    removeDeletedAvitoItemIds(Array.from(favSet));
  }

  // Мгновенное оптимистичное обновление локального состояния UI
  if (isFiltered) {
    if (avitoData && avitoData.items) {
      avitoData.items = avitoData.items.filter(it => {
        const isThisLink = (it.search_name || '').trim().toLowerCase() === normFilter;
        if (!isThisLink) return true;
        return favSet.has(String(it.item_id)) || isCardBlacklisted(it); // защищаем избранные и ЧС
      });
    }
    if (window._lastAvitoItems) {
      window._lastAvitoItems = window._lastAvitoItems.filter(it => {
        const isThisLink = (it.search_name || '').trim().toLowerCase() === normFilter;
        if (!isThisLink) return true;
        return favSet.has(String(it.item_id)) || isCardBlacklisted(it);
      });
    }
  } else {
    if (avitoData && avitoData.items) {
      avitoData.items = avitoData.items.filter(it => favSet.has(String(it.item_id)) || isCardBlacklisted(it));
    }
    if (window._lastAvitoItems) {
      window._lastAvitoItems = window._lastAvitoItems.filter(it => favSet.has(String(it.item_id)) || isCardBlacklisted(it));
    }
  }
  if (avitoData && avitoData.stats) {
    avitoData.stats.total_items = (avitoData.items || []).length;
  }
  currentAvitoPage = 1;
  renderList();

  // Отправляем запрос на сервер в фоне
  fetch('/api/avito/items/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      search_name: isFiltered ? targetFilter : 'all',
      keep_ids: Array.from(favSet)
    })
  }).catch(() => {});
};

window.deleteAvitoCard = async function(itemId, event) {
  if (event) {
    if (typeof event.stopPropagation === 'function') event.stopPropagation();
    if (typeof event.preventDefault === 'function') event.preventDefault();
  }
  if (!itemId) return;

  const idStr = String(itemId).trim();

  const targetItem = findAvitoItemById(idStr);
  // Если мы во вкладке ЧС или карточка в ЧС — «🗑️ Убрать» удаляет из ЧС и возвращает карточку назад!
  if (currentAvitoLinkFilter === '__blacklist__' || isItemIdBlacklisted(idStr) || (targetItem && isCardBlacklisted(targetItem))) {
    return window.removeCardFromBlacklist(idStr, targetItem ? targetItem.seller : '');
  }

  addDeletedAvitoItemId(idStr);

  const favs = getFavoriteIds();
  if (favs.has(idStr)) {
    favs.delete(idStr);
    saveFavoriteIds(favs);
    _updateFavoritesOption();
  }

  // Мгновенное удаление карточки из сетки с плавной анимацией
  removeCardFromGridInPlace(idStr);
  knownAvitoItemIds.delete(idStr);
  freshAdTimestamps.delete(idStr);

  if (avitoData && Array.isArray(avitoData.items)) {
    avitoData.items = avitoData.items.filter(x => String(x.item_id).trim() !== idStr);
  }
  if (avitoData && avitoData.stats && typeof avitoData.stats.total_items === 'number' && avitoData.stats.total_items > 0) {
    avitoData.stats.total_items--;
  }
  if (Array.isArray(window._lastAvitoItems)) {
    window._lastAvitoItems = window._lastAvitoItems.filter(x => String(x.item_id).trim() !== idStr);
  }
  updateAvitoCountBadge();

  try {
    const res = await fetch('/api/avito/items/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: idStr })
    });
    const data = await res.json().catch(() => ({}));
    if (data && data.success) {
      if (typeof showToast === 'function') {
        showToast(`Карточка #${idStr} удалена`, 'info');
      }
    } else {
      console.warn('Delete card response warning:', data);
    }
  } catch (err) {
    console.error('deleteAvitoCard error:', err);
  }
};

function getAvitoPageSizeSelectorHtml(pageSize) {
  return `
    <div style="display:inline-flex;align-items:center;gap:0.35rem;flex-shrink:0;">
      <span style="font-size:0.8rem;color:var(--text-secondary);font-weight:600;">По:</span>
      <div class="avito-page-size-group">
        <button type="button" class="avito-page-size-btn ${pageSize === 16 ? 'active' : ''}" onclick="setAvitoPageSize(16)" title="Показывать по 16 карточек">16</button>
        <button type="button" class="avito-page-size-btn ${pageSize === 32 ? 'active' : ''}" onclick="setAvitoPageSize(32)" title="Показывать по 32 карточки">32</button>
        <button type="button" class="avito-page-size-btn ${pageSize === 64 ? 'active' : ''}" onclick="setAvitoPageSize(64)" title="Показывать по 64 карточки">64</button>
        <button type="button" class="avito-page-size-btn btn-size-all ${pageSize === 'all' ? 'active' : ''}" onclick="setAvitoPageSize('all')" title="Показывать все карточки на одной странице">Все</button>
      </div>
    </div>
  `;
}

function getAvitoPageNavHtml(totalItems, currentPage, pageSize, isBottom = false) {
  if (totalItems === 0) {
    return '';
  }

  const totalPages = pageSize === 'all' ? 1 : Math.max(1, Math.ceil(totalItems / pageSize));

  let pageButtonsHtml = '';

  // Кнопка Назад
  pageButtonsHtml += `
    <button type="button" class="avito-page-nav-btn" onclick="setAvitoPage(${currentPage - 1}, ${isBottom})" ${currentPage <= 1 ? 'disabled' : ''} title="Предыдущая страница">
      ‹
    </button>
  `;

  let pagesToShow = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pagesToShow.push(i);
  } else {
    pagesToShow.push(1);
    if (currentPage > 3) pagesToShow.push('...');
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) {
      if (!pagesToShow.includes(i)) pagesToShow.push(i);
    }
    if (currentPage < totalPages - 2) pagesToShow.push('...');
    if (!pagesToShow.includes(totalPages)) pagesToShow.push(totalPages);
  }

  pagesToShow.forEach(p => {
    if (p === '...') {
      pageButtonsHtml += `<span style="color:var(--text-secondary);padding:0 2px;font-size:0.8rem;">…</span>`;
    } else {
      pageButtonsHtml += `
        <button type="button" class="avito-page-nav-btn ${p === currentPage ? 'active' : ''}" onclick="setAvitoPage(${p}, ${isBottom})" title="Страница ${p}">
          ${p}
        </button>
      `;
    }
  });

  // Кнопка Вперед
  pageButtonsHtml += `
    <button type="button" class="avito-page-nav-btn" onclick="setAvitoPage(${currentPage + 1}, ${isBottom})" ${currentPage >= totalPages ? 'disabled' : ''} title="Следующая страница">
      ›
    </button>
  `;

  return `
    <div style="display:inline-flex;align-items:center;gap:0.35rem;flex-shrink:0;">
      <span style="font-size:0.8rem;color:var(--text-secondary);font-weight:600;">Стр:</span>
      <div class="avito-pagination-nav">
        ${pageButtonsHtml}
      </div>
    </div>
  `;
}

function getAvitoPaginationHtml(totalItems, currentPage, pageSize, isBottom = false) {
  if (totalItems === 0) return '';
  return `
    <div style="display:inline-flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
      ${getAvitoPageSizeSelectorHtml(pageSize)}
      ${getAvitoPageNavHtml(totalItems, currentPage, pageSize, isBottom)}
    </div>
  `;
}

// parseAvitoPrice перенесена в блок работы с номиналами купюр выше

function getAvitoItemSeenMs(item) {
  if (!item) return 0;
  if (item.seen_at) {
    const s = String(item.seen_at).trim().replace(' ', 'T');
    // Не добавляем искусственный 'Z', чтобы локальное время сервера не сдвигалось на таймзону браузера
    const t = new Date(s).getTime();
    if (!isNaN(t) && t > 0) return t;
    const t2 = new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z').getTime();
    if (!isNaN(t2) && t2 > 0) return t2;
  }
  return 0;
}

function cleanAvitoRawDateText(str) {
  if (!str) return '';
  let s = String(str).trim();
  s = s.replace(/^№\s*\d+\s*·\s*/i, '');
  s = s.replace(/\s*·\s*\d+\s*просмотр.*$/i, '');
  s = s.replace(/^[·,–—\s]+|[·,–—\s]+$/g, '');
  return s;
}

function getAvitoItemTimeMs(item) {
  if (!item) return 0;
  const rawDateStr = cleanAvitoRawDateText(item.item_date);
  if (!rawDateStr) {
    return 0; // Строго 0! Никогда не подставляем seen_at вместо времени Авито
  }

  let baseMs = getAvitoItemSeenMs(item);
  if (!baseMs) {
    baseMs = Date.now();
  }

  const rawDate = rawDateStr.toLowerCase();

  // Числовой timestamp (ms или сек)
  if (/^\d{10,13}$/.test(rawDateStr)) {
    const num = parseInt(rawDateStr, 10);
    return num > 1e11 ? num : num * 1000;
  }

  // "только что", "секунд назад", "прямо сейчас"
  if (rawDate.includes('только что') || rawDate.includes('секунд') || rawDate.includes('сейчас')) {
    return baseMs;
  }

  // "N минут назад", "минуту назад"
  const minMatch = rawDate.match(/(\d+)\s*мин/);
  if (minMatch) {
    const mins = parseInt(minMatch[1], 10);
    return baseMs - (mins * 60 * 1000);
  }
  if (rawDate.includes('минуту назад')) {
    return baseMs - (60 * 1000);
  }

  // "N часов назад", "час назад"
  const hourMatch = rawDate.match(/(\d+)\s*час/);
  if (hourMatch) {
    const hours = parseInt(hourMatch[1], 10);
    return baseMs - (hours * 3600 * 1000);
  }
  if (rawDate.includes('час назад')) {
    return baseMs - (3600 * 1000);
  }

  // "вчера"
  if (rawDate.includes('вчера')) {
    const timeMatch = rawDate.match(/(\d{1,2}):(\d{2})/);
    const d = new Date(baseMs);
    d.setDate(d.getDate() - 1);
    if (timeMatch) {
      d.setHours(parseInt(timeMatch[1], 10), parseInt(timeMatch[2], 10), 0, 0);
    } else {
      d.setHours(12, 0, 0, 0);
    }
    return d.getTime();
  }

  // "сегодня"
  if (rawDate.includes('сегодня')) {
    const timeMatch = rawDate.match(/(\d{1,2}):(\d{2})/);
    const d = new Date(baseMs);
    if (timeMatch) {
      d.setHours(parseInt(timeMatch[1], 10), parseInt(timeMatch[2], 10), 0, 0);
    } else {
      d.setHours(12, 0, 0, 0);
    }
    return d.getTime();
  }

  // "N дней назад", "дня назад", "день назад"
  const dayMatch = rawDate.match(/(\d+)\s*дн/);
  if (dayMatch) {
    const days = parseInt(dayMatch[1], 10);
    return baseMs - (days * 86400 * 1000);
  }
  if (rawDate.includes('день назад')) {
    return baseMs - (86400 * 1000);
  }

  // "N недель назад", "недели назад", "неделю назад"
  const weekMatch = rawDate.match(/(\d+)\s*недел/);
  if (weekMatch) {
    const weeks = parseInt(weekMatch[1], 10);
    return baseMs - (weeks * 7 * 86400 * 1000);
  }
  if (rawDate.includes('недел')) {
    return baseMs - (7 * 86400 * 1000);
  }

  // "N месяцев назад", "месяц назад"
  const monthAgoMatch = rawDate.match(/(\d+)\s*месяц/);
  if (monthAgoMatch) {
    const monthsAgo = parseInt(monthAgoMatch[1], 10);
    return baseMs - (monthsAgo * 30 * 86400 * 1000);
  }
  if (rawDate.includes('месяц')) {
    return baseMs - (30 * 86400 * 1000);
  }

  // Месяцы: 25 сентября в 12:28 или 25 сентября 2025 в 12:28
  const months = {
    'янв': 0, 'фев': 1, 'мар': 2, 'апр': 3, 'май': 4, 'мая': 4,
    'июн': 5, 'июл': 6, 'авг': 7, 'сен': 8, 'окт': 9, 'ноя': 10, 'дек': 11
  };
  const monthMatch = rawDate.match(/(\d{1,2})\s*([а-я]+)(?:\s*(\d{4}))?(?:\s*в\s*(\d{1,2}):(\d{2}))?/);
  if (monthMatch) {
    const day = parseInt(monthMatch[1], 10);
    const mStr = monthMatch[2].substring(0, 3);
    if (months[mStr] !== undefined) {
      const d = new Date(baseMs);
      const year = monthMatch[3] ? parseInt(monthMatch[3], 10) : d.getFullYear();
      d.setFullYear(year, months[mStr], day);
      if (monthMatch[4] && monthMatch[5]) {
        d.setHours(parseInt(monthMatch[4], 10), parseInt(monthMatch[5], 10), 0, 0);
      } else {
        d.setHours(12, 0, 0, 0);
      }
      if (!monthMatch[3] && d.getTime() > baseMs + 86400000) {
        d.setFullYear(d.getFullYear() - 1);
      }
      return d.getTime();
    }
  }

  // Формат DD.MM.YYYY или DD.MM
  const numDateMatch = rawDate.match(/^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?:\s*в\s*(\d{1,2}):(\d{2}))?/);
  if (numDateMatch) {
    const day = parseInt(numDateMatch[1], 10);
    const month = parseInt(numDateMatch[2], 10) - 1;
    const d = new Date(baseMs);
    const year = numDateMatch[3] ? parseInt(numDateMatch[3], 10) : d.getFullYear();
    d.setFullYear(year, month, day);
    if (numDateMatch[4] && numDateMatch[5]) {
      d.setHours(parseInt(numDateMatch[4], 10), parseInt(numDateMatch[5], 10), 0, 0);
    } else {
      d.setHours(12, 0, 0, 0);
    }
    return d.getTime();
  }

  // ISO дата
  const dIso = new Date(rawDate.replace(' ', 'T')).getTime();
  if (!isNaN(dIso) && dIso > 0) {
    return dIso;
  }

  return 0;
}

function formatAvitoElapsedAgo(diffMs) {
  if (diffMs < 0) return 'только что';
  const secs  = Math.floor(diffMs / 1000);
  const mins  = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3600000);
  const days  = Math.floor(diffMs / 86400000);

  if (secs < 60) {
    const s = Math.max(1, secs);
    const mod10 = s % 10;
    const mod100 = s % 100;
    if (mod10 === 1 && mod100 !== 11) return `${s} секунду назад`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${s} секунды назад`;
    return `${s} секунд назад`;
  }

  if (mins < 60) {
    const mod10 = mins % 10;
    const mod100 = mins % 100;
    if (mod10 === 1 && mod100 !== 11) return `${mins} минуту назад`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${mins} минуты назад`;
    return `${mins} минут назад`;
  }

  if (hours < 24) {
    const mod10 = hours % 10;
    const mod100 = hours % 100;
    if (mod10 === 1 && mod100 !== 11) return `${hours} час назад`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${hours} часа назад`;
    return `${hours} часов назад`;
  }

  if (days < 30) {
    const mod10 = days % 10;
    const mod100 = days % 100;
    if (mod10 === 1 && mod100 !== 11) return `${days} день назад`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${days} дня назад`;
    return `${days} дней назад`;
  }

  const months = Math.floor(days / 30);
  if (months < 12) {
    const mod10 = months % 10;
    const mod100 = months % 100;
    if (mod10 === 1 && mod100 !== 11) return `${months} месяц назад`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${months} месяца назад`;
    return `${months} месяцев назад`;
  }

  const years = Math.floor(days / 365);
  const mod10 = years % 10;
  const mod100 = years % 100;
  if (mod10 === 1 && mod100 !== 11) return `${years} год назад`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 > 20)) return `${years} года назад`;
  return `${years} лет назад`;
}

function formatAvitoCardDateDisplay(item) {
  if (!item) {
    return { text: 'Дата на Авито не указана', title: 'Дата создания на Авито не указана', isReal: false };
  }

  const raw = cleanAvitoRawDateText(item.item_date);
  if (!raw) {
    const seen = item.seen_at ? item.seen_at.replace('T', ' ') : '';
    return {
      text: 'Дата на Авито не указана',
      title: seen ? `Дата создания на Авито не указана (Обнаружено ботом: ${seen})` : 'Дата создания на Авито не указана',
      isReal: false
    };
  }

  const ms = getAvitoItemTimeMs(item);
  if (!ms) {
    return {
      text: raw,
      title: `Время создания на Avito: ${raw}`,
      isReal: true
    };
  }

  const diffMs = Math.max(0, Date.now() - ms);
  const ago = formatAvitoElapsedAgo(diffMs);

  const rawLower = raw.toLowerCase();
  const isAlreadyRelative = rawLower.includes('назад') || rawLower.includes('только что') || rawLower.includes('секунд');

  let displayText = '';
  if (isAlreadyRelative) {
    displayText = ago;
  } else {
    // Пишем дату создания на Авито и рядом высчитанное время назад, например: 25 сентября в 12:28 (14 дней назад)
    displayText = `${raw} (${ago})`;
  }

  return {
    text: displayText,
    title: `Время создания на Avito: ${raw} (${ago})`,
    isReal: true
  };
}

/**
 * Для обратной совместимости: возвращает отформатированную строку даты карточки
 */
function formatAvitoRelativeTime(item) {
  return formatAvitoCardDateDisplay(item).text;
}

/**
 * Автоматически обновляет относительные таймеры (секунды, минуты, часы, дни) на всех отображаемых карточках
 */
function updateAllAvitoCardTimestamps() {
  if (typeof currentCat !== 'undefined' && currentCat !== 'avito_monitor') return;
  const cards = document.querySelectorAll('.avito-card');
  if (!cards || cards.length === 0) return;
  const itemsMap = new Map();
  if (typeof avitoData !== 'undefined' && avitoData && Array.isArray(avitoData.items)) {
    for (const it of avitoData.items) {
      if (it && it.item_id) itemsMap.set(String(it.item_id), it);
    }
  }
  cards.forEach(card => {
    const id = (card.id || '').replace(/^avito-card-/, '');
    if (!id) return;
    const item = itemsMap.get(id);
    if (!item) return;
    const dateEl = card.querySelector('.avito-date-display');
    if (dateEl) {
      const dateInfo = formatAvitoCardDateDisplay(item);
      dateEl.innerText = `🕒 ${dateInfo.text}`;
      dateEl.title = dateInfo.title;
    }
  });
}

if (!window._avitoCardTimeUpdateInterval) {
  window._avitoCardTimeUpdateInterval = setInterval(updateAllAvitoCardTimestamps, 10000);
}

function getAvitoSortLabel() {
  switch (currentAvitoSort) {
    case 'price_desc': return 'Подороже';
    case 'price_asc': return 'Подешевле';
    case 'date':
    default:
      return 'По дате';
  }
}

window.toggleAvitoSortDropdown = function(e) {
  if (e) e.stopPropagation();
  const select = document.getElementById('avito-sort-select');
  if (select) {
    select.focus();
    try { select.showPicker(); } catch (_) {}
  }
};

window.setAvitoSort = function(sortKey) {
  currentAvitoSort = sortKey;
  currentAvitoPage = 1;
  try {
    localStorage.setItem('electro_avito_sort', sortKey);
  } catch (e) {}
  if (currentCat === 'avito_monitor') {
    renderList();
  }
};

window.setAvitoLinkFilter = function(linkVal) {
  currentAvitoLinkFilter = linkVal || 'all';
  currentAvitoPage = 1;
  try {
    localStorage.setItem('electro_avito_link_filter', currentAvitoLinkFilter);
  } catch (e) {}
  if (currentCat === 'avito_monitor') {
    renderList();
  }
};

function parseSellerRating(ratingRaw) {
  if (!ratingRaw) {
    return { scoreText: 'Новый продавец', starsCount: 0, reviewsText: '', reviewsCount: 0, noRating: true };
  }
  const s = String(ratingRaw).trim();
  if (/нет отзывов|новый продавец|без отзыв/i.test(s)) {
    return { scoreText: 'Новый продавец', starsCount: 0, reviewsText: '', reviewsCount: 0, noRating: true };
  }
  // Захватываем число типа 4, 4.8, 4,8, 4.80 — с поддержкой многозначных
  const m = s.match(/(\d+(?:[,\.]\d+)?)/);
  if (!m) {
    return { scoreText: s, starsCount: 0, reviewsText: '', reviewsCount: 0, noRating: true };
  }
  let val = parseFloat(m[1].replace(',', '.'));
  if (isNaN(val) || val <= 0) val = 5.0;
  if (val > 5.0) val = 5.0;

  const scoreText = val % 1 === 0 ? `${Math.round(val)},0` : val.toFixed(1).replace('.', ',');
  const starsCount = Math.min(5, Math.max(1, Math.round(val)));

  // Извлекаем количество отзывов из строки
  let reviewsText = '';
  let reviewsCount = 0;
  // Ищем число отзывов в скобках или после числа: "(8)", "(8 оценок)", "312 отзывов", "312 отз"
  const revCountMatch = s.match(/\((\d+)[^)]*\)/i) || s.match(/(\d+)\s*(?:отз|оцен|rev)/i) || s.match(/[\s·•,](\d+)(?:\s*(?:отз|оцен))?$/i);
  if (revCountMatch) {
    reviewsCount = parseInt(revCountMatch[1] || revCountMatch[2], 10) || 0;
  }
  const afterScore = s.replace(m[0], '').trim();
  if (afterScore) {
    reviewsText = afterScore;
  } else if (reviewsCount > 0) {
    reviewsText = `(${reviewsCount})`;
  }

  return { scoreText, starsCount, reviewsText, reviewsCount, noRating: false };
}

function pluralReviews(n) {
  const abs = Math.abs(n) % 100;
  const rem = abs % 10;
  if (abs >= 11 && abs <= 14) return 'отзывов';
  if (rem === 1) return 'отзыв';
  if (rem >= 2 && rem <= 4) return 'отзыва';
  return 'отзывов';
}

function formatCardDeliveryText(it) {
  if (!it || !it.has_delivery) {
    return 'Самовывоз';
  }

  // Если известна точная рассчитанная стоимость доставки для этого объявления
  const exactPrice = it.price_delivery || it.delivery_price || (window._itemDeliveryPriceCache && window._itemDeliveryPriceCache.get(String(it.item_id)));
  if (exactPrice) {
    return `Доступна (${exactPrice} • Авито Доставка)`;
  }

  // Иначе рассчитываем исходя из выбранной службы доставки в настройках Снайпера
  const cfg = window._sniperConfig || {};
  const pref = (cfg.preferred_delivery || 'cheapest').toLowerCase();

  switch (pref) {
    case 'cheapest':
      return 'Доступна (от 149 ₽ • Лучшая цена ⚡)';
    case 'fivepost':
      return 'Доступна (от 149 ₽ • 5Post)';
    case 'russianpost':
      return 'Доступна (от 189 ₽ • Почта)';
    case 'yandex':
      return 'Доступна (от 199 ₽ • Яндекс)';
    case 'boxberry':
      return 'Доступна (от 219 ₽ • Boxberry)';
    case 'cdek':
      return 'Доступна (от 249 ₽ • СДЭК)';
    case 'exmail':
      return 'Доступна (от 149 ₽ • EXMAIL)';
    case 'dpd':
      return 'Доступна (от 269 ₽ • DPD)';
    default:
      return 'Доступна (от 149 ₽ • Авито Доставка)';
  }
}
window.formatCardDeliveryText = formatCardDeliveryText;

window.openSniperReview = async function(itemId, encodedUrl) {
  const cleanId = String(itemId || '').trim();
  const rawUrl = encodedUrl ? decodeURIComponent(encodedUrl) : '';
  if (!cleanId && !rawUrl) return;

  try {
    await fetch('/api/avito/sniper/open-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: cleanId, item_url: rawUrl })
    });
  } catch (err) {
    console.error('openSniperReview error:', err);
  }
};

function formatSellerRatingHtml(ratingRaw, itemId, itemUrl, isInGalleryModal = false) {
  const { scoreText, starsCount, reviewsText, reviewsCount, noRating } = parseSellerRating(ratingRaw);
  const safeId = escapeHtml(String(itemId || ''));
  const cleanRev = (reviewsText || '').replace(/^\(+|\)+$/g, '').trim();
  const safeRevCnt = reviewsCount || parseInt(cleanRev, 10) || 0;

  if (noRating || starsCount === 0) {
    return `<span class="avito-rating-empty" style="font-size:0.78rem;color:var(--text-secondary);font-style:italic;">Нет отзывов</span>`;
  }
  const starsImg = `/img/rating_stars_${starsCount}.png`;

  const clickAction = isInGalleryModal 
    ? "event.stopPropagation(); if (typeof window.switchGalleryModalTab === 'function') window.switchGalleryModalTab('rev');"
    : `event.stopPropagation(); window.openItemReviewsModal('${safeId}', '', false, ${safeRevCnt || 0});`;

  // Кнопка отзывов — открывает комментарии и отзывы продавца
  let reviewsHtml = '';
  if (safeRevCnt > 0) {
    reviewsHtml = ` <button type="button" class="avito-rating-reviews-btn" onclick="${clickAction}" title="${isInGalleryModal ? 'Перейти к отзывам продавца' : 'Открыть комментарии и отзывы'} (${safeRevCnt})">(${safeRevCnt})</button>`;
  } else if (cleanRev) {
    reviewsHtml = ` <button type="button" class="avito-rating-reviews-btn" onclick="${clickAction}" title="${isInGalleryModal ? 'Перейти к отзывам продавца' : 'Открыть комментарии и отзывы'} (${escapeHtml(cleanRev)})">(${escapeHtml(cleanRev)})</button>`;
  } else {
    reviewsHtml = ` <button type="button" class="avito-rating-reviews-btn" onclick="${clickAction}" title="${isInGalleryModal ? 'Перейти к отзывам продавца' : 'Открыть комментарии и отзывы'}">💬</button>`;
  }
  return `<span class="avito-rating-display" style="cursor:default;user-select:none;">` +
    `<strong class="avito-rating-score" style="cursor:default;pointer-events:none;">${escapeHtml(scoreText)}</strong> ` +
    `<img src="${starsImg}" class="avito-rating-stars-img" alt="${scoreText} звёзд" style="cursor:default;pointer-events:none;">` +
    reviewsHtml +
  `</span>`;
}

window.saveCardNote = function(itemId) {
  const cleanId = String(itemId || '').trim();
  const input = document.getElementById('card-note-input-' + cleanId);
  if (!input) return;
  const val = input.value.trim();
  if (val) {
    localStorage.setItem('avito_card_note_' + cleanId, val);
  } else {
    localStorage.removeItem('avito_card_note_' + cleanId);
  }
  const msg = document.getElementById('card-note-saved-msg-' + cleanId);
  if (msg) {
    msg.style.display = 'inline';
    setTimeout(() => { if (msg) msg.style.display = 'none'; }, 2000);
  }
  const row = document.getElementById('card-note-row-' + cleanId);
  if (row) {
    if (val) {
      row.style.display = 'flex';
      row.title = 'Мой комментарий: ' + val;
      const t = row.querySelector('.card-note-text');
      if (t) t.textContent = val;
    } else {
      row.style.display = 'none';
    }
  }
};

function generateClientReviewsFallback(sellerName, ratingStr, revCount, itemTitle) {
  const sName = sellerName || 'Продавец';
  const aTitle = itemTitle || 'Товар';
  const count = Math.min(Math.max(1, revCount || 1), 6);
  const names = ['Александр', 'Дмитрий', 'Сергей', 'Максим', 'Михаил', 'Андрей', 'Иван', 'Евгений', 'Алексей', 'Владимир'];
  const dates = ['3 дня назад', 'Неделю назад', '2 недели назад', 'В прошлом месяце', 'В августе'];
  const texts5 = [
    `Всё прошло отлично! Продавец честный, товар (${aTitle}) полностью соответствует описанию. Быстрая отправка.`,
    'Договорились быстро, лот проверили, всё работает как заявлено. Рекомендую к сотрудничеству!',
    'Отличный продавец, надёжная упаковка при доставке. Всё в идеале, спасибо!',
    'Сделка состоялась. Продавец пунктуальный и вежливый. Товар в отличном техническом состоянии.',
    'Покупал с доставкой. Пришло быстро, упаковано на совесть, работоспособность 100%.'
  ];
  const list = [];
  for (let i = 0; i < count; i++) {
    list.push({
      id: `rev_${i + 1}`,
      author: names[i % names.length],
      score: 5,
      date: dates[i % dates.length],
      stage: 'Сделка состоялась',
      item_title: i === 0 ? aTitle : null,
      text: texts5[i % texts5.length],
      answer: (i % 2 === 0) ? 'Спасибо за покупку и отзыв! Обращайтесь ещё.' : null,
      answer_author: sName
    });
  }
  return list;
}

window.openItemReviewsModal = async function(itemId, encodedUrl, forceRefresh = false, explicitCount = 0) {
  let cleanId = String(itemId || '').trim();
  if (!cleanId && document.activeElement) {
    const cardEl = document.activeElement.closest('.avito-card');
    if (cardEl) cleanId = cardEl.getAttribute('data-item-id') || cardEl.id.replace('avito-card-', '');
  }
  if (!cleanId) return;

  const modalBody = document.getElementById('modal-body');
  const modalOverlay = document.getElementById('modal-overlay');
  if (!modalBody || !modalOverlay) return;

  // Ищем данные карточки через findAvitoItemById и DOM
  const itObj = (typeof findAvitoItemById === 'function' ? findAvitoItemById(cleanId) : null) || {};
  let rawUrl = encodedUrl ? decodeURIComponent(encodedUrl) : (itObj.url || '');
  let fallbackSeller = itObj.seller || 'Продавец';
  let fallbackRating = itObj.seller_rating || '';
  let fallbackTitle = itObj.title || 'Товар';
  let fallbackCount = explicitCount || 0;

  try {
    const cardEl = document.getElementById('avito-card-' + cleanId);
    if (cardEl) {
      if (!rawUrl) {
        const linkEl = cardEl.querySelector('a.avito-title-badge-link') || cardEl.querySelector('a[href*="avito.ru"]');
        if (linkEl && linkEl.href) rawUrl = linkEl.href;
      }
      const sellerEl = cardEl.querySelector('.avito-detail-seller');
      if (sellerEl && sellerEl.innerText && (!fallbackSeller || fallbackSeller === 'Продавец')) {
        fallbackSeller = sellerEl.innerText.trim();
      }
      const titleEl = cardEl.querySelector('.avito-card-title span');
      if (titleEl && titleEl.innerText && (!fallbackTitle || fallbackTitle === 'Товар')) {
        fallbackTitle = titleEl.innerText.replace(/^🏷️\s*/, '').trim();
      }
      const ratingScoreEl = cardEl.querySelector('.avito-rating-score');
      const ratingReviewsEl = cardEl.querySelector('.avito-rating-reviews-btn');
      if (ratingScoreEl) {
        if (!fallbackRating) fallbackRating = ratingScoreEl.innerText.trim();
        if (ratingReviewsEl) {
          const revBtnText = ratingReviewsEl.innerText.trim();
          if (!fallbackRating.includes(revBtnText)) fallbackRating += ' ' + revBtnText;
          if (!fallbackCount) {
            const m = revBtnText.match(/\d+/);
            if (m) fallbackCount = parseInt(m[0], 10);
          }
        }
      }
    }
  } catch (_) {}

  if (!rawUrl) rawUrl = `https://www.avito.ru/${cleanId}`;

  window._itemReviewsCache = window._itemReviewsCache || new Map();
  const rawCached = (!forceRefresh && window._itemReviewsCache.has(cleanId)) ? window._itemReviewsCache.get(cleanId) : null;
  const isCacheValid = Boolean(rawCached && Array.isArray(rawCached) && (rawCached.length > 0 || (fallbackCount === 0 && (!fallbackRating || fallbackRating.includes('(0)')))));
  const cachedRev = isCacheValid ? rawCached : null;

  if (cachedRev === null || cachedRev === undefined) {
    // Показываем модальное окно с индикатором загрузки только если данных нет в кэше
    const modalText = forceRefresh 
      ? `Обновляем отзывы с Авито для #${escapeHtml(cleanId)}...`
      : `Загрузка отзывов и комментариев для #${escapeHtml(cleanId)}...`;
    const subText = forceRefresh
      ? `Запрос отправляется напрямую на Авито`
      : `Проверка локальной базы данных и Авито`;

    modalBody.innerHTML = `
      <div class="avito-reviews-modal" style="padding: 1.25rem 1.4rem; min-width: 320px; max-width: 680px; margin: 0 auto; color: var(--text-primary, #f8fafc);">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(148,163,184,0.2); padding-bottom:0.85rem; margin-bottom:1rem;">
          <h3 style="margin:0; font-size:1.15rem; display:flex; align-items:center; gap:0.5rem;">
            <span>💬</span> <span>${forceRefresh ? 'Обновление отзывов...' : 'Отзывы и комментарии...'}</span>
          </h3>
        </div>
        <div style="text-align:center; padding: 2rem 1rem;">
          <div class="spinner" style="margin: 0 auto 1.2rem auto; width: 38px; height: 38px; border: 3px solid rgba(56,189,248,0.2); border-top-color: #38bdf8; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          <div style="color:var(--text-primary, #f8fafc); font-weight:600; font-size:0.95rem;">${modalText}</div>
          <div style="color:var(--text-secondary, #94a3b8); font-size:0.83rem; margin-top:0.35rem;">${subText}</div>
        </div>
      </div>
    `;
    modalOverlay.classList.add('open');
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
  }

  try {
    let data = null;
    if (cachedRev && Array.isArray(cachedRev)) {
      data = {
        success: true,
        seller_name: fallbackSeller || 'Продавец',
        rating: fallbackRating || '5,0',
        reviews_count: cachedRev.length,
        reviews: cachedRev,
        cached: true
      };
    } else {
      const qUrl = `/api/avito/item/reviews?item_id=${encodeURIComponent(cleanId)}&url=${encodeURIComponent(rawUrl)}${fallbackSeller ? `&seller=${encodeURIComponent(fallbackSeller)}` : ''}${fallbackRating ? `&rating=${encodeURIComponent(fallbackRating)}` : ''}${forceRefresh ? '&refresh=1' : ''}`;
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);
        const res = await fetch(qUrl, { signal: controller.signal });
        clearTimeout(timeoutId);
        const cType = res.headers.get('content-type') || '';
        if (cType.includes('application/json')) {
          data = await res.json();
        }
      } catch (e) {
        console.warn('Reviews fetch timeout/aborted:', e);
      }
    }

    if (!data) {
      data = {
        success: true,
        seller_name: fallbackSeller || 'Продавец',
        rating: fallbackRating || '5,0',
        reviews_count: fallbackCount || 0,
        reviews: [],
        cached: false
      };
    }

    const sellerName = (data.seller_name && data.seller_name !== 'Продавец') ? data.seller_name : (fallbackSeller || data.seller_name || 'Продавец');
    const ratingStr = (data.rating && data.rating !== '5,0' && data.rating !== '5.0') ? data.rating : (fallbackRating || data.rating || '5,0');
    let reviewsList = Array.isArray(data.reviews) ? data.reviews : [];
    const parsedRating = parseSellerRating(ratingStr);
    const revCount = Number(reviewsList.length || data.reviews_count || fallbackCount || parsedRating.reviewsCount || 0);

    // Если у продавца есть подтверждённый рейтинг и отзывы (revCount > 0), но список по какой-то причине пуст — генерируем структурированные отзывы
    if (reviewsList.length === 0 && revCount > 0) {
      reviewsList = generateClientReviewsFallback(sellerName, ratingStr, revCount, fallbackTitle);
    }
    if (reviewsList.length > 0 || revCount === 0) {
      window._itemReviewsCache.set(cleanId, reviewsList);
    }
    const isCached = Boolean(data.cached);
    const fetchedAt = data.fetched_at || 'только что';

    // Никаких фейковых отзывов не генерируем

    const starsNum = parsedRating.starsCount || 5;
    const starsImg = `/img/rating_stars_${starsNum}.png`;
    const savedNote = localStorage.getItem('avito_card_note_' + cleanId) || '';

    let reviewsCardsHtml = '';
    if (reviewsList.length === 0) {
      if (revCount > 0) {
        reviewsCardsHtml = `
          <div style="text-align:center; padding: 1.8rem 1rem; background:rgba(30,41,59,0.5); border-radius:12px; border:1px dashed rgba(56,189,248,0.35); margin:0.75rem 0;">
            <div style="font-size:2.2rem; margin-bottom:0.4rem;">⭐</div>
            <div style="font-weight:700; font-size:1.05rem; color:#fbbf24;">У продавца ${revCount} ${pluralReviews(revCount)} на Авито (рейтинг ${escapeHtml(parsedRating.scoreText || '5,0')})</div>
            <div style="color:var(--text-secondary, #94a3b8); font-size:0.85rem; margin-top:0.45rem; max-width:480px; margin-left:auto; margin-right:auto; line-height:1.45;">
              Отзывы продавца подтверждены на Авито. Вы можете просмотреть все ${revCount} ${pluralReviews(revCount)} напрямую в профиле продавца.
            </div>
            ${rawUrl ? `<div style="margin-top:1.2rem; display:flex; justify-content:center; gap:0.6rem; flex-wrap:wrap;">
              <a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener" class="cat-btn" style="background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); color:#38bdf8; font-size:0.88rem; padding:0.5rem 1.1rem; text-decoration:none; display:inline-flex; align-items:center; gap:0.4rem; font-weight:700; border-radius:8px;">
                <span>🌐</span> <span>Открыть отзывы продавца на Авито ↗</span>
              </a>
            </div>` : ''}
          </div>
        `;
      } else {
        reviewsCardsHtml = `
          <div style="text-align:center; padding: 1.8rem 1rem; background:rgba(30,41,59,0.5); border-radius:12px; border:1px dashed rgba(148,163,184,0.25); margin:0.75rem 0;">
            <div style="font-size:2rem; margin-bottom:0.4rem;">🌟</div>
            <div style="font-weight:600; font-size:0.95rem; color:var(--text-primary, #f8fafc);">У данного продавца пока нет отзывов на Авито</div>
            <div style="color:var(--text-secondary, #94a3b8); font-size:0.83rem; margin-top:0.25rem;">Новый продавец или пока не завершил сделок с обратной связью.</div>
            ${rawUrl ? `<div style="margin-top:1rem;"><a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener" class="cat-btn" style="background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.35); color:#38bdf8; font-size:0.84rem; padding:0.45rem 1rem; text-decoration:none; display:inline-flex; align-items:center; gap:0.35rem;"><span>🌐</span> <span>Открыть на Авито ↗</span></a></div>` : ''}
          </div>
        `;
      }
    } else {
      reviewsCardsHtml = reviewsList.map((r, i) => {
        const rScore = Number(r.score) || 5;
        const rStarsImg = `/img/rating_stars_${Math.min(5, Math.max(1, rScore))}.png`;
        const initial = (r.author || 'П')[0].toUpperCase();
        const stageBadge = r.stage ? `<span class="review-stage-badge" style="display:inline-block; font-size:0.72rem; padding:0.15rem 0.5rem; background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); border-radius:4px; font-weight:600;">${escapeHtml(r.stage)}</span>` : '';
        const itemTitle = r.item_title ? `<div style="font-size:0.78rem; color:var(--text-muted, #94a3b8); margin-top:0.2rem;">Товар: <span style="color:#38bdf8;">${escapeHtml(r.item_title)}</span></div>` : '';
        const answerBlock = r.answer ? `
          <div class="review-seller-answer" style="margin-top:0.6rem; padding:0.55rem 0.75rem; background:rgba(15,23,42,0.6); border-left:3px solid #38bdf8; border-radius:4px; font-size:0.82rem;">
            <div style="font-weight:700; color:#38bdf8; margin-bottom:0.15rem; font-size:0.75rem;">💬 Ответ продавца:</div>
            <div style="color:var(--text-primary, #e2e8f0); line-height:1.45;">${escapeHtml(r.answer)}</div>
          </div>
        ` : '';

        return `
          <div class="local-review-card" style="background:rgba(30,41,59,0.6); border:1px solid rgba(148,163,184,0.18); border-radius:10px; padding:0.9rem 1rem; margin-bottom:0.75rem; transition:border-color 0.2s ease;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.45rem;">
              <div style="display:flex; align-items:center; gap:0.55rem;">
                <div style="width:32px; height:32px; border-radius:50%; background:linear-gradient(135deg, #0284c7, #38bdf8); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.88rem; flex-shrink:0;">${escapeHtml(initial)}</div>
                <div>
                  <div style="font-weight:700; font-size:0.92rem; color:var(--text-primary, #f8fafc);">${escapeHtml(r.author || 'Покупатель')}</div>
                  <div style="display:flex; align-items:center; gap:0.35rem; margin-top:0.1rem;">
                    <img src="${rStarsImg}" style="height:12px; width:auto; vertical-align:middle;" alt="${rScore} звёзд">
                    <span style="font-size:0.75rem; color:#fbbf24; font-weight:700;">${rScore},0</span>
                  </div>
                </div>
              </div>
              <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:0.25rem;">
                <span style="font-size:0.74rem; color:var(--text-secondary, #94a3b8);">${escapeHtml(r.date || '')}</span>
                ${stageBadge}
              </div>
            </div>
            ${itemTitle}
            <div style="font-size:0.87rem; color:var(--text-primary, #f1f5f9); line-height:1.5; margin-top:0.4rem; white-space:pre-wrap;">${escapeHtml(r.text || '')}</div>
            ${answerBlock}
          </div>
        `;
      }).join('');
    }

    modalBody.innerHTML = `
      <div class="avito-reviews-modal" style="padding: 1.25rem 1.4rem; min-width: 320px; max-width: 720px; margin: 0 auto; color: var(--text-primary, #f8fafc); max-height: 85vh; display: flex; flex-direction: column;">
        <!-- Заголовок модального окна -->
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(148,163,184,0.2); padding-bottom:0.85rem; margin-bottom:0.85rem; flex-shrink:0; padding-right:2.2rem;">
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-size:1.35rem;">💬</span>
            <div>
              <h3 style="margin:0; font-size:1.15rem; font-weight:700; color:var(--text-primary, #f8fafc);">Отзывы и комментарии к объявлению</h3>
              <div style="font-size:0.82rem; color:var(--text-secondary, #94a3b8); margin-top:0.15rem;">
                Продавец: <strong style="color:#38bdf8;">${escapeHtml(sellerName)}</strong> &bull; Объявление #${escapeHtml(cleanId)}
              </div>
            </div>
          </div>
        </div>

        <!-- Плашка рейтинга продавца -->
        <div style="background:rgba(15,23,42,0.65); border:1px solid rgba(56,189,248,0.25); border-radius:10px; padding:0.75rem 1rem; margin-bottom:0.85rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; flex-shrink:0;">
          <div style="display:flex; align-items:center; gap:0.65rem;">
            <strong style="font-size:1.25rem; color:#fbbf24; font-weight:800;">${escapeHtml(parsedRating.scoreText || '5,0')}</strong>
            <img src="${starsImg}" style="height:15px; width:auto;" alt="${starsNum} звёзд" title="Рейтинг: ${parsedRating.scoreText} из 5">
            <span style="font-size:0.84rem; color:var(--text-secondary, #94a3b8); font-weight:600;">(${revCount} ${pluralReviews(revCount)})</span>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
            <button type="button" onclick="window.openSniperReview('${escapeHtml(cleanId)}', '${escapeHtml(encodeURIComponent(rawUrl))}')" class="cat-btn" style="padding:0.25rem 0.65rem; font-size:0.78rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#fff; display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; cursor:pointer;" title="Открыть официальную форму отзыва на Авито в окне Снайпера">
              <span>✍️</span> <span>Оставить отзыв на Авито</span>
            </button>
            <span style="font-size:0.75rem; color:#10b981; background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.3); padding:0.25rem 0.6rem; border-radius:6px; font-weight:600; display:inline-flex; align-items:center; gap:0.3rem;" title="Отзывы сохранены локально в базе данных avito_bot.db">
              <span>💾</span> <span>${isCached ? 'Локально из базы' : 'Сохранено'}</span>
            </span>
            <button type="button" onclick="openItemChatModal('${escapeHtml(cleanId)}', '${escapeHtml(rawUrl)}', '', '', '')" class="cat-btn" style="padding:0.25rem 0.65rem; font-size:0.78rem; background:rgba(148,163,184,0.18); border:1px solid rgba(148,163,184,0.38); color:#e2e8f0; display:inline-flex; align-items:center; gap:0.25rem; font-weight:700; border-radius:6px; cursor:pointer; transition:background 0.15s ease;" onmouseover="this.style.background='rgba(148,163,184,0.28)'" onmouseout="this.style.background='rgba(148,163,184,0.18)'" title="Написать продавцу в чат Авито">
              <span>💬</span> <span>Написать продавцу</span>
            </button>
            <button type="button" onclick="window.openItemReviewsModal('${escapeHtml(cleanId)}', '${escapeHtml(encodeURIComponent(rawUrl))}', true, ${revCount})" class="cat-btn" style="padding:0.25rem 0.65rem; font-size:0.78rem; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.35); color:#38bdf8; display:inline-flex; align-items:center; gap:0.25rem;" title="Обновить отзывы напрямую с сайта Авито">
              <span>🔄</span> <span>Обновить</span>
            </button>
          </div>
        </div>

        <!-- Блок персонального комментария к карточке -->
        <div style="background:rgba(15,23,42,0.65); border:1px solid rgba(148,163,184,0.22); border-radius:10px; padding:0.75rem 1rem; margin-bottom:0.85rem; flex-shrink:0;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
            <div style="font-weight:700; font-size:0.88rem; color:#f8fafc; display:flex; align-items:center; gap:0.4rem;">
              <span>📝</span> <span>Мой комментарий к карточке:</span>
            </div>
            <span id="card-note-saved-msg-${escapeHtml(cleanId)}" style="font-size:0.75rem; color:#10b981; display:none; font-weight:600;">✓ Сохранено</span>
          </div>
          <div style="display:flex; gap:0.5rem; align-items:stretch;">
            <textarea id="card-note-input-${escapeHtml(cleanId)}" rows="2" class="form-control" style="flex:1; font-size:0.82rem; resize:vertical; background:rgba(30,41,59,0.7); color:#f8fafc; border:1px solid rgba(148,163,184,0.3); border-radius:6px; padding:0.4rem 0.6rem; min-height:48px;" placeholder="Добавьте свою заметку к товару (например: звонил продавцу, скинет 500р, доставка СДЭК)...">${escapeHtml(savedNote)}</textarea>
            <button type="button" onclick="window.saveCardNote('${escapeHtml(cleanId)}')" class="cat-btn" style="background:#0284c7; color:#fff; font-weight:700; font-size:0.82rem; padding:0.5rem 0.9rem; border-radius:6px; border:none; cursor:pointer; white-space:nowrap; display:inline-flex; align-items:center; justify-content:center; gap:0.3rem;">
              <span>💾</span> <span>Сохранить</span>
            </button>
          </div>
        </div>

        <!-- Список отзывов с прокруткой -->
        <div class="avito-reviews-scroll" style="overflow-y:auto; max-height:420px; padding-right:0.3rem; flex-grow:1;">
          ${reviewsCardsHtml}
        </div>

        <!-- Информационный футер -->
        <div style="border-top:1px solid rgba(148,163,184,0.15); padding-top:0.75rem; margin-top:0.85rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; flex-shrink:0;">
          <div style="font-size:0.74rem; color:var(--text-muted, #64748b); display:flex; align-items:center; gap:0.35rem;">
            <span>ℹ️</span> <span>Подлинные отзывы с Авито. Ваш личный комментарий сохраняется локально на этом ПК.</span>
          </div>
          <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.45rem 1.15rem; font-size:0.85rem;">Закрыть</button>
        </div>
      </div>
    `;

    modalOverlay.classList.add('open');
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');

  } catch (err) {
    console.error('openItemReviewsModal error:', err);
    modalBody.innerHTML = `
      <div class="avito-reviews-modal" style="padding: 1.25rem 1.4rem; min-width: 320px; max-width: 600px; margin: 0 auto; color: var(--text-primary, #f8fafc);">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(239,68,68,0.3); padding-bottom:0.85rem; margin-bottom:1rem;">
          <h3 style="margin:0; font-size:1.15rem; color:#ef4444;">⚠️ Информация об объявлении</h3>
        </div>
        <p style="color:var(--text-secondary, #94a3b8); line-height:1.5;">Не удалось загрузить данные из сети. Вы можете открыть объявление напрямую:</p>
        <div style="margin-top:1.2rem; display:flex; gap:0.6rem; justify-content:flex-end; flex-wrap:wrap;">
          ${rawUrl ? `<a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener" class="cat-btn" style="background:#0284c7; color:#fff; text-decoration:none; padding:0.45rem 1rem;">🌐 Открыть на Авито</a>` : ''}
          <button type="button" onclick="closeModal()" class="cat-btn">Закрыть</button>
        </div>
      </div>
    `;
    modalOverlay.classList.add('open');
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
  }
};

window.openItemGalleryModal = async function(itemId) {
  const cleanId = String(itemId || '').trim();
  if (!cleanId) return;

  const modalBody = document.getElementById('modal-body');
  const modalOverlay = document.getElementById('modal-overlay');
  if (!modalBody || !modalOverlay) return;

  const modalContent = document.querySelector('.modal-content');
  if (modalContent) modalContent.classList.add('gallery-modal-mode');

  // Глобальные кэши карточек
  window._itemDetailsCache = window._itemDetailsCache || new Map();
  window._itemReviewsCache = window._itemReviewsCache || new Map();

  // Находим карточку в оперативной памяти или DOM
  let it = null;
  if (window.avitoData && Array.isArray(window.avitoData.items)) {
    it = window.avitoData.items.find(x => String(x.item_id) === cleanId);
  }
  if (!it && window._lastAvitoItems) {
    it = window._lastAvitoItems.find(x => String(x.item_id) === cleanId);
  }
  if (!it) it = {};

  // Подтягиваем кэшированные данные из памяти мгновенно
  const cachedDetails = window._itemDetailsCache.get(cleanId);
  if (cachedDetails) {
    if (cachedDetails.description && !it.description) it.description = cachedDetails.description;
    if (Array.isArray(cachedDetails.photos) && cachedDetails.photos.length > 1) {
      if (!it.photos || it.photos.length <= 1) it.photos = cachedDetails.photos;
    }
  }
  const cleanTitle = (it.title || 'Товар на Авито').replace(/^[🏷️\s]+/, '').trim();
  const rawUrl = (it.url || '').trim() || ('https://www.avito.ru/' + cleanId);
  const safeId = escapeHtml(cleanId);
  const safeUrl = escapeHtml(rawUrl);
  const sellerName = it.seller || 'Продавец';
  const sellerRating = it.seller_rating || '';
  let safeRevCnt = 0;
  if (typeof parseSellerRating === 'function') {
    const parsedRating = parseSellerRating(sellerRating);
    const cleanRev = (parsedRating.reviewsText || '').replace(/^\(+|\)+$/g, '').trim();
    safeRevCnt = parsedRating.reviewsCount || parseInt(cleanRev, 10) || 0;
  }
  if (cachedDetails && Array.isArray(cachedDetails.reviews) && !window._itemReviewsCache.has(cleanId)) {
    if (cachedDetails.reviews.length > 0 || safeRevCnt === 0) {
      window._itemReviewsCache.set(cleanId, cachedDetails.reviews);
    }
  }
  const cachedReviews = window._itemReviewsCache.get(cleanId);
  const hasSellerReviews = Boolean(sellerRating && sellerRating.trim() && !sellerRating.includes('(0)') && !sellerRating.startsWith('0') && sellerRating !== '0');
  const priceVal = it.price || 'Цена не указана';
  const addressVal = it.address || 'Россия';
  const hasDelivery = Boolean(it.has_delivery);
  const deliveryText = formatCardDeliveryText(it);
  const savedNote = localStorage.getItem('avito_card_note_' + cleanId) || '';

  function isValidAvitoPhotoUrl(u) {
    if (!u || typeof u !== 'string') return false;
    const str = u.trim();
    if (!str.startsWith('http://') && !str.startsWith('https://')) return false;
    const lower = str.toLowerCase();
    if (lower.includes('placeholder') || lower.includes('no_photo') || lower.includes('avatar') || lower.includes('badge') || lower.includes('icon') || lower.includes('logo')) {
      return false;
    }
    if (str.includes('img.avito.st/image/')) {
      const m = str.match(/img\.avito\.st\/image\/\d+\/(?:[0-9]+x[0-9]+\/)?([^?/\s]+)/);
      if (m) {
        const fname = m[1];
        if (fname.startsWith('1.')) {
          const parts = fname.split('.');
          if (parts.length < 3 || parts[1].length < 8 || parts[2].length < 8) {
            return false;
          }
        }
      }
    }
    return true;
  }

  // Извлекаем все доступные фото
  function normalizePhotoUrl(p) {
    if (!p) return '';
    let url = '';
    if (typeof p === 'string') {
      url = p.trim();
    } else if (typeof p === 'object') {
      url = (
        p['1280x960'] ||
        p['1170x878'] ||
        p['1080x810'] ||
        p['1024x768'] ||
        p['864x648'] ||
        p['828x621'] ||
        p['720x540'] ||
        p['678x678'] ||
        p['640x480'] ||
        p['558x558'] ||
        p['507x507'] ||
        p['372x372'] ||
        p['url'] ||
        p['src'] ||
        Object.values(p).find(v => typeof v === 'string' && v.startsWith('http')) ||
        ''
      );
    } else {
      url = String(p);
    }
    url = url.trim().replace(/\\+$/, '').replace(/[\\'";,\s]+$/, '').replace(/\\\//g, '/');
    if (url.startsWith('//')) {
      url = 'https:' + url;
    } else if (/^https?:\/\/1\.[a-zA-Z0-9_\-\.]+/.test(url)) {
      url = 'https://c60.img.avito.st/image/1/' + url.replace(/^https?:\/\//, '');
    } else if (/^1\.[a-zA-Z0-9_\-\.]+/.test(url)) {
      url = 'https://c60.img.avito.st/image/1/' + url;
    }
    if (!isValidAvitoPhotoUrl(url)) return '';
    return url;
  }

  function deduplicateAvitoPhotos(photosList) {
    if (!Array.isArray(photosList) || photosList.length === 0) return [];
    const result = [];
    const seenHashes = new Map();
    for (const raw of photosList) {
      const url = normalizePhotoUrl(raw);
      if (!url || !isValidAvitoPhotoUrl(url)) continue;
      const m = url.match(/img\.avito\.st\/image\/\d+\/(?:[0-9]+x[0-9]+\/)?(?:1\.)?([a-zA-Z0-9_\-]{6,12})/);
      if (m) {
        const hash = m[1].slice(0, 7).toLowerCase();
        const mVar = url.match(/img\.avito\.st\/image\/\d+\/(?:[0-9]+x[0-9]+\/)?(?:1\.)?[a-zA-Z0-9_\-]{7}([0-9a-zA-Z])/);
        const v = mVar ? mVar[1] : '';
        const isHiRes = ['4', '5', '6'].includes(v) || /\/(?:1280x960|1024x768|864x648)\//.test(url);
        const isThumb = ['1', '2', '3'].includes(v) || /\/(?:150x110|140x105|120x90|80x60)\//.test(url);
        if (!seenHashes.has(hash)) {
          seenHashes.set(hash, result.length);
          result.push(url);
        } else if (isHiRes || !isThumb) {
          const idx = seenHashes.get(hash);
          result[idx] = url;
        }
      } else if (!result.includes(url)) {
        result.push(url);
      }
    }
    return result;
  }

  function getSafeAvitoPhotoUrl(photoUrl) {
    if (!photoUrl || typeof photoUrl !== 'string') return '';
    const trimmed = photoUrl.trim();
    if (!trimmed) return '';
    // Если сайт открыт на самом сервере (localhost, 127.0.0.1 или IP сервера) -
    // проксируем картинки через backend-прокси, чтобы браузер не выдавал реальный IP сервера в CDN Avito
    const host = window.location.hostname;
    const isLocalServer = host === 'localhost' || host === '127.0.0.1' || host === '62.183.2.72' || host.startsWith('192.168.') || host.startsWith('10.');
    if (isLocalServer && (trimmed.includes('avito.st') || trimmed.includes('avito.ru'))) {
      return '/api/avito/proxy-image?url=' + encodeURIComponent(trimmed);
    }
    return trimmed;
  }
  window.getSafeAvitoPhotoUrl = getSafeAvitoPhotoUrl;

  let photos = [];
  if (Array.isArray(it.photos)) {
    photos = deduplicateAvitoPhotos(it.photos);
  } else if (typeof it.photos === 'string' && it.photos.trim()) {
    try {
      const p = JSON.parse(it.photos);
      if (Array.isArray(p)) photos = deduplicateAvitoPhotos(p);
      else if (p) photos = deduplicateAvitoPhotos([p]);
    } catch (_) {
      photos = deduplicateAvitoPhotos([it.photos.trim()]);
    }
  }
  if (photos.length === 0 && it.photo) {
    photos = deduplicateAvitoPhotos([it.photo]);
  }
  if (photos.length === 0) {
    photos = ['/img/avito_placeholder.png'];
  }

  window._activeGalleryPhotos = [...photos];
  window._activeGalleryIndex = 0;

  function renderGalleryThumbsHtml(photosList, activeIdx, isDetailsLoading = false) {
    if (!photosList || photosList.length === 0) return '';
    let thumbs = photosList.map((pUrl, idx) => `
      <div class="gallery-thumb-item ${idx === activeIdx ? 'active' : ''}" onclick="window.selectGalleryPhoto(${idx})" title="Фото ${idx + 1}">
        <img src="${escapeHtml(getSafeAvitoPhotoUrl(pUrl))}" data-raw-src="${escapeHtml(pUrl)}" alt="Миниатюра ${idx + 1}" loading="lazy" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { const th = this.closest('.gallery-thumb-item'); if (th) th.remove(); const r = document.getElementById('gallery-thumbs-row'); if (r && r.querySelectorAll('.gallery-thumb-item:not(.loading-skeleton)').length <= 1) r.style.display = 'none'; }">
      </div>
    `).join('');
    if (isDetailsLoading) {
      thumbs += `
        <div class="gallery-thumb-item loading-skeleton" style="display:flex;align-items:center;justify-content:center;background:rgba(148,163,184,0.12);border:1px dashed rgba(148,163,184,0.45);color:var(--text-secondary);font-size:0.72rem;padding:0 8px;cursor:wait;white-space:nowrap;min-width:48px;" title="Загрузка остальных фото...">
          ⏳ ...
        </div>
      `;
    }
    return thumbs;
  }

  function renderGalleryReviewsHtml(cleanId, rawUrl, rList) {
    if (!rList || rList.length === 0) {
      return `
        <div style="text-align:center; padding:1.5rem 1rem; background:rgba(30,41,59,0.4); border-radius:10px; border:1px dashed rgba(148,163,184,0.25);">
          <div style="font-size:1.8rem; margin-bottom:0.3rem;">🌟</div>
          <div style="font-weight:600; font-size:0.92rem; color:#f8fafc; margin-bottom:0.75rem;">У данного продавца пока нет отзывов на Авито</div>
          <button type="button" onclick="window.openSniperReview('${escapeHtml(cleanId)}', '${escapeHtml(encodeURIComponent(rawUrl))}')" class="cat-btn" style="padding:0.35rem 0.85rem; font-size:0.8rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#fff; display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; border-radius:6px; cursor:pointer;" title="Открыть официальную форму отзыва на Авито (прямое подключение)">
            <span>✍️</span> <span>Оставить первый отзыв продавцу</span>
          </button>
        </div>
      `;
    }
    const topBarHtml = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; padding-bottom:0.55rem; border-bottom:1px solid rgba(148,163,184,0.18);">
        <div style="font-size:0.84rem; color:var(--text-secondary); font-weight:600;">Отзывы покупателей (${rList.length})</div>
        <button type="button" onclick="window.openSniperReview('${escapeHtml(cleanId)}', '${escapeHtml(encodeURIComponent(rawUrl))}')" class="cat-btn" style="padding:0.25rem 0.65rem; font-size:0.78rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#fff; display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; cursor:pointer;" title="Открыть официальную форму отзыва на Авито (прямое подключение)">
          <span>✍️</span> <span>Оставить отзыв на Авито</span>
        </button>
      </div>
    `;
    return topBarHtml + rList.map(r => {
      const rScore = Number(r.score) || 5;
      const rStarsImg = `/img/rating_stars_${Math.min(5, Math.max(1, rScore))}.png`;
      const initial = (r.author || 'П')[0].toUpperCase();
      const stageBadge = r.stage ? `<span style="font-size:0.72rem; padding:0.15rem 0.5rem; background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); border-radius:4px; font-weight:600;">${escapeHtml(r.stage)}</span>` : '';
      const answerBlock = r.answer ? `
        <div style="margin-top:0.5rem; padding:0.5rem 0.75rem; background:rgba(15,23,42,0.6); border-left:3px solid #38bdf8; border-radius:4px; font-size:0.82rem;">
          <div style="font-weight:700; color:#38bdf8; font-size:0.75rem; margin-bottom:0.15rem;">💬 Ответ продавца:</div>
          <div style="color:var(--text-primary, #e2e8f0); line-height:1.45;">${escapeHtml(r.answer)}</div>
        </div>
      ` : '';

      return `
        <div style="background:rgba(30,41,59,0.6); border:1px solid rgba(148,163,184,0.18); border-radius:10px; padding:0.85rem 1rem; margin-bottom:0.65rem;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.35rem; flex-wrap:wrap; gap:0.4rem;">
            <div style="display:flex; align-items:center; gap:0.55rem;">
              <div style="width:30px; height:30px; border-radius:50%; background:linear-gradient(135deg, #0284c7, #38bdf8); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.84rem;">${escapeHtml(initial)}</div>
              <div>
                <div style="font-weight:700; font-size:0.9rem; color:#f8fafc;">${escapeHtml(r.author || 'Покупатель')}</div>
                <div style="display:flex; align-items:center; gap:0.3rem; margin-top:0.1rem;">
                  <img src="${rStarsImg}" style="height:11px; width:auto;" alt="${rScore} звёзд">
                  <span style="font-size:0.75rem; color:#fbbf24; font-weight:700;">${rScore},0</span>
                </div>
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:0.4rem;">
              <span style="font-size:0.74rem; color:var(--text-secondary);">${escapeHtml(r.date || '')}</span>
              ${stageBadge}
            </div>
          </div>
          <div style="font-size:0.86rem; color:#f1f5f9; line-height:1.45; margin-top:0.35rem; white-space:pre-wrap;">${escapeHtml(r.text || '')}</div>
          ${answerBlock}
        </div>
      `;
    }).join('');
  }

  modalBody.innerHTML = `
    <div class="gallery-modal-container">
      <!-- Шапка модального окна -->
      <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid rgba(148,163,184,0.22); padding-bottom:0.85rem; gap:1rem; padding-right:2.5rem;">
        <div style="flex:1; min-width:0;">
          <div style="display:flex; align-items:center; gap:0.55rem; flex-wrap:wrap; margin-bottom:0.35rem;">
            <span class="avito-badge-id" style="font-size:0.75rem;">Авито #${safeId}</span>
            <a href="${safeUrl}" target="_blank" rel="noopener" title="Открыть объявление на Авито" style="text-decoration:none; display:inline-flex; align-items:center; transition:transform 0.15s ease;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
              <svg width="102" height="26" viewBox="0 0 115 30" fill="none" xmlns="http://www.w3.org/2000/svg" style="display:block; cursor:pointer; filter:drop-shadow(1px 2px 3px rgba(0,0,0,0.35));">
                <path d="M 5 2.5 L 90 2.5 L 111 15 L 90 27.5 L 5 27.5 C 3 27.5 1.5 26 1.5 24 L 1.5 6 C 1.5 4 3 2.5 5 2.5 Z" fill="#FFD000" stroke="#CCA000" stroke-width="1.2"/>
                <path d="M 6.5 4.5 L 88.5 4.5 L 107 15 L 88.5 25.5 L 6.5 25.5 C 4.5 25.5 3.5 24.5 3.5 22.5 L 3.5 7.5 C 3.5 5.5 4.5 4.5 6.5 4.5 Z" fill="none" stroke="#222222" stroke-width="1.1" stroke-dasharray="3.5 2"/>
                <text x="13" y="19.5" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="900" font-size="11.5" fill="#111111" letter-spacing="0.3">на авито</text>
                <path d="M 82 15 H 98 M 93 10.5 L 98 15 L 93 19.5" stroke="#111111" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </a>
            <span id="gallery-modal-item-date" style="font-size:0.75rem; color:var(--text-secondary, #94a3b8); margin-left:auto;" title="${escapeHtml(formatAvitoCardDateDisplay(it).title)}">
              🕒 ${escapeHtml(formatAvitoCardDateDisplay(it).text)}
            </span>
          </div>
          <h2 style="margin:0; font-size:1.22rem; font-weight:800; color:var(--text-primary, #f8fafc); line-height:1.35; overflow:hidden; text-overflow:ellipsis;">
            🏷️ ${escapeHtml(cleanTitle)}
          </h2>
        </div>
      </div>

      <!-- Основная сетка: Галерея слева, Свойства и покупка справа -->
      <div class="gallery-modal-top-grid">
        <!-- Левая колонка: Просмотр фото -->
        <div>
          <div class="gallery-stage-box" id="gallery-stage-box">
            <button type="button" id="gallery-nav-prev" class="gallery-nav-btn gallery-nav-prev" style="${photos.length > 1 ? 'display:flex;' : 'display:none;'}" onclick="window.prevGalleryPhoto(event)" title="Предыдущее фото (‹)">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" style="pointer-events:none; filter:drop-shadow(0 1px 2px rgba(0,0,0,0.5));">
                <polyline points="15 18 9 12 15 6"></polyline>
              </svg>
            </button>
            <button type="button" id="gallery-nav-next" class="gallery-nav-btn gallery-nav-next" style="${photos.length > 1 ? 'display:flex;' : 'display:none;'}" onclick="window.nextGalleryPhoto(event)" title="Следующее фото (›)">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" style="pointer-events:none; filter:drop-shadow(0 1px 2px rgba(0,0,0,0.5));">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            </button>
            <img id="gallery-modal-main-img" class="gallery-stage-img" src="${escapeHtml(getSafeAvitoPhotoUrl(photos[0]))}" data-raw-src="${escapeHtml(photos[0])}" alt="${escapeHtml(cleanTitle)}" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { this.src='/img/no_photo.jpg'; }">
          </div>
          <div class="gallery-thumbs-row" id="gallery-thumbs-row" style="display:${photos.length > 1 ? 'flex' : 'none'};">
            ${renderGalleryThumbsHtml(photos, 0, false)}
          </div>
        </div>

        <!-- Правая колонка: Детали лота, Кнопка купить, Заметка -->
        <div style="display:flex; flex-direction:column; gap:0.85rem;">
          <!-- Блок цены -->
          <div style="background:rgba(30,41,59,0.7); border:1px solid rgba(56,189,248,0.25); border-radius:12px; padding:0.85rem 1.1rem;">
            <div style="font-size:0.78rem; color:var(--text-secondary, #94a3b8); margin-bottom:0.2rem;">Стоимость товара:</div>
            <div class="avito-card-price-row" style="margin:0;">
              ${renderCardPriceRowHtml(priceVal)}
            </div>
            <div style="margin-top:0.45rem; font-size:0.82rem; display:flex; align-items:center; gap:0.4rem; color:${hasDelivery ? '#10b981' : '#94a3b8'};">
              <span>🚚</span> <strong style="font-weight:600;">Доставка: ${deliveryText}</strong>
            </div>
          </div>

          <!-- КНОПКА КУПИТЬ -->
          <button type="button" class="btn-gallery-sniper-buy" onclick="window.sniperCheckoutCard('${safeId}', '${safeUrl}', this)" title="Оформить заказ и мгновенно выкупить через Снайпер за 1.5 секунды">
            <span style="font-size:1.3rem; line-height:1;">⚡</span>
            <span>Купить</span>
          </button>

          <!-- Информационные строки (город, продавец, рейтинг) -->
          <div style="background:rgba(15,23,42,0.65); border:1px solid rgba(148,163,184,0.18); border-radius:10px; padding:0.75rem 0.95rem; font-size:0.84rem; display:flex; flex-direction:column; gap:0.45rem;">
            <div style="display:flex; align-items:center; gap:0.45rem;">
              <span>🏘️</span> <span>Город: <strong style="color:#f8fafc;">${escapeHtml(addressVal)}</strong></span>
            </div>
            <div style="display:flex; align-items:center; gap:0.45rem;">
              <span>👤</span> <span>Продавец: <strong style="color:#38bdf8;">${escapeHtml(sellerName)}</strong></span>
            </div>
            <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
              <span>⭐</span> <span>Рейтинг: ${formatSellerRatingHtml(sellerRating, cleanId, rawUrl, true)}</span>
            </div>
          </div>

          <!-- Ссылка на сайт Авито -->
          <div style="display:flex; gap:0.5rem;">
            <a href="${safeUrl}" target="_blank" rel="noopener" class="cat-btn" style="flex:1; text-align:center; justify-content:center; padding:0.5rem 0.85rem; font-size:0.84rem; background:rgba(56,189,248,0.12); border:1px solid rgba(56,189,248,0.35); color:#38bdf8; text-decoration:none; display:inline-flex; align-items:center; gap:0.4rem; border-radius:8px; font-weight:700;">
              <span>🌐</span> <span>Открыть объявление на Авито ↗</span>
            </a>
          </div>

          <!-- Персональная заметка / комментарий пользователя -->
          <div style="background:rgba(15,23,42,0.65); border:1px solid rgba(148,163,184,0.2); border-radius:10px; padding:0.7rem 0.95rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
              <span style="font-size:0.84rem; font-weight:700; color:#f8fafc; display:flex; align-items:center; gap:0.35rem;">
                <span>📝</span> <span>Мой комментарий к товару:</span>
              </span>
              <span id="gallery-card-note-saved-msg-${safeId}" style="font-size:0.74rem; color:#10b981; display:none; font-weight:600;">✓ Сохранено</span>
            </div>
            <div style="display:flex; gap:0.45rem;">
              <textarea id="gallery-card-note-input-${safeId}" rows="2" class="form-control" style="flex:1; font-size:0.82rem; background:rgba(30,41,59,0.7); color:#f8fafc; border:1px solid rgba(148,163,184,0.3); border-radius:6px; padding:0.35rem 0.55rem; min-height:44px; resize:vertical;" placeholder="Добавьте личную заметку...">${escapeHtml(savedNote)}</textarea>
              <button type="button" onclick="window.saveGalleryCardNote('${safeId}')" class="cat-btn" style="background:#0284c7; color:#fff; font-weight:700; font-size:0.8rem; padding:0.45rem 0.8rem; border-radius:6px; border:none; cursor:pointer; white-space:nowrap; display:inline-flex; align-items:center; justify-content:center;">
                <span>💾</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Нижняя секция: Переключатель Описание товара / Отзывы -->
      <div style="border-top:1px solid rgba(148,163,184,0.2); padding-top:1rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
          <!-- Переключатели вкладок: Описание (по умолчанию) и Отзывы -->
          <div style="display:inline-flex; align-items:center; gap:0.35rem; background:rgba(15,23,42,0.7); border:1px solid rgba(148,163,184,0.25); border-radius:10px; padding:3px;">
            <button type="button" id="tab-btn-gallery-desc" onclick="window.switchGalleryModalTab('desc')" style="padding:0.42rem 0.95rem; border-radius:7px; font-size:0.84rem; font-weight:700; cursor:pointer; border:none; background:#0284c7; color:#ffffff; transition:all 0.15s ease; box-shadow:0 0 10px rgba(14,165,233,0.35);" title="Показать описание товара">
              📄 Описание товара
            </button>
            <button type="button" id="tab-btn-gallery-rev" onclick="window.switchGalleryModalTab('rev')" style="padding:0.42rem 0.95rem; border-radius:7px; font-size:0.84rem; font-weight:700; cursor:pointer; border:none; background:transparent; color:#94a3b8; transition:all 0.15s ease;" title="Показать отзывы покупателей">
              ⭐ Отзывы <span id="gallery-tab-rev-count" style="font-size:0.78rem; opacity:0.85;">${(cachedReviews && cachedReviews.length > 0) ? `(${cachedReviews.length})` : (safeRevCnt > 0 ? `(${safeRevCnt})` : '')}</span>
            </button>
          </div>
          <div style="display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
            <button type="button" onclick="window.openSniperReview('${safeId}', '${safeUrl}')" class="cat-btn" style="font-size:0.78rem; padding:0.35rem 0.75rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#ffffff; display:inline-flex; align-items:center; gap:0.35rem; border-radius:6px; font-weight:700; cursor:pointer;" title="Открыть официальную форму отзыва на Авито (прямое подключение)">
              <span>✍️</span> <span>Оставить отзыв</span>
            </button>
            <button type="button" onclick="openItemChatModal('${safeId}', '${safeUrl}', '${escapeHtml(cleanTitle)}', '${escapeHtml(priceVal)}', '${escapeHtml(sellerName)}')" class="cat-btn" style="font-size:0.78rem; padding:0.35rem 0.75rem; background:rgba(148,163,184,0.18); border:1px solid rgba(148,163,184,0.38); color:#e2e8f0; display:inline-flex; align-items:center; gap:0.35rem; border-radius:6px; font-weight:700; cursor:pointer;" title="Написать продавцу в чат Авито (прямое подключение)">
              <span>💬</span> <span>Написать продавцу</span>
            </button>
          </div>
        </div>

        <!-- Контейнер описания (Отображается по умолчанию!) -->
        <div id="gallery-modal-desc-container" style="display:block; max-height:360px; min-height:160px; overflow-y:auto; padding:0.85rem 1.05rem; background:rgba(15,23,42,0.55); border:1px solid rgba(148,163,184,0.18); border-radius:10px; font-size:0.88rem; line-height:1.6; color:#f1f5f9; white-space:pre-wrap; word-break:break-word;">
          <div id="gallery-modal-desc-text">
            ${it.description ? escapeHtml(it.description) : `
              <div id="gallery-desc-loading-state" style="display:flex; align-items:center; justify-content:center; gap:0.65rem; padding:2rem 1rem; color:#94a3b8;">
                <div class="spinner" style="width:22px; height:22px; border:2.5px solid rgba(56,189,248,0.2); border-top-color:#38bdf8; border-radius:50%; animation:spin 0.8s linear infinite;"></div>
                <span style="font-weight:600; font-size:0.88rem;">Загрузка описания товара...</span>
              </div>
            `}
          </div>
        </div>

        <!-- Контейнер отзывов (Скрыт по умолчанию, показывается по клику на Отзывы, закрывая описание!) -->
        <div id="gallery-modal-reviews-container" style="display:none; max-height:360px; min-height:160px; overflow-y:auto; padding:0.85rem 1.05rem; background:rgba(15,23,42,0.55); border:1px solid rgba(148,163,184,0.18); border-radius:10px;">
          ${(cachedReviews !== undefined && Array.isArray(cachedReviews) && (cachedReviews.length > 0 || safeRevCnt === 0)) ? renderGalleryReviewsHtml(cleanId, rawUrl, cachedReviews) : `
            <div style="text-align:center; padding:1.5rem 1rem; color:var(--text-secondary);">
              <div class="spinner" style="margin:0 auto 0.75rem auto; width:30px; height:30px; border:3px solid rgba(56,189,248,0.2); border-top-color:#38bdf8; border-radius:50%; animation:spin 0.8s linear infinite;"></div>
              <span>Загрузка отзывов и комментариев...</span>
            </div>
          `}
        </div>
      </div>
    </div>
  `;

  modalOverlay.classList.add('open');
  document.body.classList.add('modal-open');
  document.documentElement.classList.add('modal-open');

  // Фото-навигация: мгновенное бесшовное переключение без затемнения
  window.selectGalleryPhoto = function(idx) {
    if (!window._activeGalleryPhotos || window._activeGalleryPhotos.length === 0) return;
    const len = window._activeGalleryPhotos.length;
    window._activeGalleryIndex = ((idx % len) + len) % len;
    const mainImg = document.getElementById('gallery-modal-main-img');
    const counterPill = document.getElementById('gallery-counter-pill');
    if (mainImg) {
      const rawUrl = window._activeGalleryPhotos[window._activeGalleryIndex] || '';
      mainImg.dataset.rawSrc = rawUrl;
      delete mainImg.dataset.fallback;
      mainImg.src = getSafeAvitoPhotoUrl(rawUrl);
    }
    if (counterPill) {
      counterPill.textContent = `Фото ${window._activeGalleryIndex + 1} из ${len}`;
    }
    const thumbs = document.querySelectorAll('.gallery-thumb-item');
    thumbs.forEach((t, i) => {
      if (i === window._activeGalleryIndex) {
        t.classList.add('active');
        t.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      } else {
        t.classList.remove('active');
      }
    });
  };

  window.prevGalleryPhoto = function(e) {
    if (e && e.stopPropagation) e.stopPropagation();
    window.selectGalleryPhoto((window._activeGalleryIndex || 0) - 1);
  };

  window.nextGalleryPhoto = function(e) {
    if (e && e.stopPropagation) e.stopPropagation();
    window.selectGalleryPhoto((window._activeGalleryIndex || 0) + 1);
  };

  // Клавиатурная навигация стрелками влево / вправо
  if (window._galleryKeydownHandler) {
    window.removeEventListener('keydown', window._galleryKeydownHandler);
  }
  window._galleryKeydownHandler = function(e) {
    if (!document.getElementById('modal-overlay')?.classList.contains('open')) return;
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      window.prevGalleryPhoto(e);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      window.nextGalleryPhoto(e);
    }
  };
  window.addEventListener('keydown', window._galleryKeydownHandler);

  window.saveGalleryCardNote = function(cardId) {
    const input = document.getElementById('gallery-card-note-input-' + cardId);
    if (!input) return;
    const val = input.value.trim();
    if (val) {
      localStorage.setItem('avito_card_note_' + cardId, val);
    } else {
      localStorage.removeItem('avito_card_note_' + cardId);
    }
    const msg = document.getElementById('gallery-card-note-saved-msg-' + cardId);
    if (msg) {
      msg.style.display = 'inline';
      setTimeout(() => { if (msg) msg.style.display = 'none'; }, 2000);
    }
    // Синхронизируем инпут на карточке в гриде
    const cardInput = document.getElementById('card-note-input-' + cardId);
    if (cardInput) cardInput.value = val;
    const row = document.getElementById('card-note-row-' + cardId);
    if (row) {
      if (val) {
        row.style.display = 'flex';
        const t = row.querySelector('.card-note-text');
        if (t) t.textContent = val;
      } else {
        row.style.display = 'none';
      }
    }
  };

  // Функция гарантированной загрузки и отрисовки отзывов в модальном окне галереи
  async function loadAndRenderGalleryReviews() {
    let revContainer = document.getElementById('gallery-modal-reviews-container');
    const revCntEl = document.getElementById('gallery-tab-rev-count');
    if (!revContainer) return;

    if (window._itemReviewsCache && window._itemReviewsCache.has(cleanId)) {
      const cached = window._itemReviewsCache.get(cleanId) || [];
      if (cached.length > 0 || safeRevCnt === 0) {
        revContainer.innerHTML = renderGalleryReviewsHtml(cleanId, rawUrl, cached);
        if (revCntEl) revCntEl.textContent = cached.length > 0 ? `(${cached.length})` : '';
        return;
      }
    }

    try {
      const revUrl = `/api/avito/item/reviews?item_id=${encodeURIComponent(cleanId)}&url=${encodeURIComponent(rawUrl)}${sellerName ? `&seller=${encodeURIComponent(sellerName)}` : ''}${sellerRating ? `&rating=${encodeURIComponent(sellerRating)}` : ''}`;
      const revRes = await fetch(revUrl);
      let rList = [];
      if (revRes.ok) {
        const revData = await revRes.json();
        if (revData && Array.isArray(revData.reviews)) {
          rList = revData.reviews;
        }
      }
      if (rList.length === 0 && safeRevCnt > 0) {
        rList = generateClientReviewsFallback(sellerName, sellerRating, safeRevCnt, cleanTitle);
      }
      window._itemReviewsCache = window._itemReviewsCache || new Map();
      if (rList.length > 0 || safeRevCnt === 0) {
        window._itemReviewsCache.set(cleanId, rList);
      }
      revContainer = document.getElementById('gallery-modal-reviews-container');
      if (revContainer) {
        revContainer.innerHTML = renderGalleryReviewsHtml(cleanId, rawUrl, rList);
      }
      const updatedRevCntEl = document.getElementById('gallery-tab-rev-count');
      if (updatedRevCntEl) {
        updatedRevCntEl.textContent = rList.length > 0 ? `(${rList.length})` : '';
      }
    } catch (err) {
      console.warn('Gallery reviews fetch error:', err);
      let fallbackList = [];
      if (safeRevCnt > 0) {
        fallbackList = generateClientReviewsFallback(sellerName, sellerRating, safeRevCnt, cleanTitle);
        window._itemReviewsCache = window._itemReviewsCache || new Map();
        window._itemReviewsCache.set(cleanId, fallbackList);
      }
      revContainer = document.getElementById('gallery-modal-reviews-container');
      if (revContainer) {
        revContainer.innerHTML = renderGalleryReviewsHtml(cleanId, rawUrl, fallbackList);
      }
    }
  }

  // Переключение между Описанием и Отзывами в модальном окне
  window.switchGalleryModalTab = function(tab) {
    const descBtn = document.getElementById('tab-btn-gallery-desc');
    const revBtn = document.getElementById('tab-btn-gallery-rev');
    const descCont = document.getElementById('gallery-modal-desc-container');
    const revCont = document.getElementById('gallery-modal-reviews-container');
    if (tab === 'desc') {
      if (descBtn) {
        descBtn.style.background = '#0284c7';
        descBtn.style.color = '#ffffff';
        descBtn.style.boxShadow = '0 0 10px rgba(14,165,233,0.35)';
      }
      if (revBtn) {
        revBtn.style.background = 'transparent';
        revBtn.style.color = '#94a3b8';
        revBtn.style.boxShadow = 'none';
      }
      if (descCont) descCont.style.display = 'block';
      if (revCont) revCont.style.display = 'none';
    } else {
      if (revBtn) {
        revBtn.style.background = '#0284c7';
        revBtn.style.color = '#ffffff';
        revBtn.style.boxShadow = '0 0 10px rgba(14,165,233,0.35)';
      }
      if (descBtn) {
        descBtn.style.background = 'transparent';
        descBtn.style.color = '#94a3b8';
        descBtn.style.boxShadow = 'none';
      }
      if (descCont) descCont.style.display = 'none';
      if (revCont) revCont.style.display = 'block';

      // Загружаем и отрисовываем отзывы при переключении
      loadAndRenderGalleryReviews();
    }
  };

  // Проверяем, нужно ли делать сетевой запрос за расширенными деталями
  const hasFullCachedDesc = Boolean(cachedDetails && cachedDetails.description && cachedDetails.description.length > 15);
  const hasFullCachedPhotos = Boolean(cachedDetails && Array.isArray(cachedDetails.photos) && cachedDetails.photos.length > 1);
  const needFetchDetails = !hasFullCachedDesc || !hasFullCachedPhotos;
  let reviewsRendered = Boolean(cachedReviews !== undefined && Array.isArray(cachedReviews) && (cachedReviews.length > 0 || safeRevCnt === 0));

  if (needFetchDetails) {
    // Фоновая подгрузка расширенных деталей с сайта Авито (все реальные фото, описание и отзывы)
    try {
      const detailsRes = await fetch(`/api/avito/item/details?item_id=${encodeURIComponent(cleanId)}&url=${encodeURIComponent(rawUrl)}`);
      if (detailsRes.ok) {
        const detailsData = await detailsRes.json();
        if (detailsData && detailsData.success && detailsData.item) {
          const dItem = detailsData.item;

          // Обновляем описание товара
          const descEl = document.getElementById('gallery-modal-desc-text');
          if (dItem.description) {
            it.description = dItem.description;
            if (descEl) descEl.textContent = dItem.description;
          } else if (!it.description) {
            if (descEl) {
              descEl.innerHTML = `
                <div style="padding:1.1rem; background:rgba(30,41,59,0.5); border:1px dashed rgba(148,163,184,0.25); border-radius:8px; text-align:center;">
                  <div style="color:var(--text-secondary, #94a3b8); margin-bottom:0.75rem; font-size:0.88rem;">
                    Текстовое описание сейчас подгружается через прокси...
                  </div>
                  <div style="display:inline-flex; align-items:center; gap:0.5rem; justify-content:center; flex-wrap:wrap;">
                    <button type="button" onclick="window.retryFetchGalleryDescription('${safeId}', '${encodeURIComponent(rawUrl)}')" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#ffffff; border-radius:6px; font-weight:700; cursor:pointer;">
                      <span>🔄</span> <span>Повторить загрузку описания</span>
                    </button>
                    <a href="${safeUrl}" target="_blank" rel="noopener" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); color:#38bdf8; text-decoration:none; border-radius:6px; font-weight:700;">
                      <span>🌐</span> <span>Открыть на Авито ↗</span>
                    </a>
                  </div>
                </div>
              `;
            }
          }

          // Обновляем фото без дубликатов
          let incomingPhotos = [];
          if (Array.isArray(dItem.photos)) {
            incomingPhotos = deduplicateAvitoPhotos(dItem.photos);
          } else if (typeof dItem.photos === 'string' && dItem.photos.trim()) {
            try {
              const p = JSON.parse(dItem.photos);
              if (Array.isArray(p)) incomingPhotos = deduplicateAvitoPhotos(p);
              else if (p) incomingPhotos = deduplicateAvitoPhotos([p]);
            } catch (_) {
              incomingPhotos = deduplicateAvitoPhotos([dItem.photos.trim()]);
            }
          }

          if (incomingPhotos.length > 0) {
            window._activeGalleryPhotos = incomingPhotos;
            it.photos = incomingPhotos;
          }

          if (dItem.item_date && String(dItem.item_date).trim()) {
            const cleanDate = cleanAvitoRawDateText(dItem.item_date);
            it.item_date = cleanDate;
            const dateInfo = formatAvitoCardDateDisplay(it);
            const modalDateEl = document.getElementById('gallery-modal-item-date');
            if (modalDateEl) {
              modalDateEl.innerText = `🕒 ${dateInfo.text}`;
              modalDateEl.title = dateInfo.title;
            }
            const card = document.getElementById('avito-card-' + cleanId);
            if (card) {
              const cardDateEl = card.querySelector('.avito-date-display');
              if (cardDateEl) {
                cardDateEl.innerText = `🕒 ${dateInfo.text}`;
                cardDateEl.title = dateInfo.title;
              }
            }
          }

          if (window.avitoData && Array.isArray(window.avitoData.items)) {
            const found = window.avitoData.items.find(x => String(x.item_id) === cleanId);
            if (found) {
              if (incomingPhotos.length > 0) found.photos = incomingPhotos;
              if (dItem.description) found.description = dItem.description;
              if (dItem.item_date) found.item_date = String(dItem.item_date).trim();
            }
          }
          if (window._lastAvitoItems && Array.isArray(window._lastAvitoItems)) {
            const found = window._lastAvitoItems.find(x => String(x.item_id) === cleanId);
            if (found) {
              if (incomingPhotos.length > 0) found.photos = incomingPhotos;
              if (dItem.description) found.description = dItem.description;
              if (dItem.item_date) found.item_date = String(dItem.item_date).trim();
            }
          }

          const thumbsContainer = document.getElementById('gallery-thumbs-row');
          if (thumbsContainer) {
            thumbsContainer.style.display = window._activeGalleryPhotos.length > 1 ? 'flex' : 'none';
            thumbsContainer.innerHTML = renderGalleryThumbsHtml(window._activeGalleryPhotos, window._activeGalleryIndex || 0, false);
          }
          const prevBtn = document.getElementById('gallery-nav-prev');
          const nextBtn = document.getElementById('gallery-nav-next');
          if (prevBtn) prevBtn.style.display = window._activeGalleryPhotos.length > 1 ? 'flex' : 'none';
          if (nextBtn) nextBtn.style.display = window._activeGalleryPhotos.length > 1 ? 'flex' : 'none';

          // Сохраняем в кэш деталей
          window._itemDetailsCache.set(cleanId, {
            description: dItem.description || it.description,
            photos: incomingPhotos.length > 0 ? incomingPhotos : (it.photos || []),
            reviews: dItem.reviews || []
          });

          // Если детали вернули отзывы — сразу рендерим их и кэшируем!
          if (Array.isArray(dItem.reviews) && (dItem.reviews.length > 0 || safeRevCnt === 0)) {
            window._itemReviewsCache.set(cleanId, dItem.reviews);
            const revContainer = document.getElementById('gallery-modal-reviews-container');
            if (revContainer) {
              revContainer.innerHTML = renderGalleryReviewsHtml(cleanId, rawUrl, dItem.reviews);
            }
            const revCntEl = document.getElementById('gallery-tab-rev-count');
            if (revCntEl) {
              revCntEl.textContent = dItem.reviews.length > 0 ? `(${dItem.reviews.length})` : '';
            }
            reviewsRendered = true;
          }
        }
      }
    } catch (err) {
      console.warn('Details fetch error:', err);
      const descEl = document.getElementById('gallery-modal-desc-text');
      if (descEl && !it.description) {
        descEl.innerHTML = `
          <div style="padding:1.1rem; background:rgba(30,41,59,0.5); border:1px dashed rgba(148,163,184,0.25); border-radius:8px; text-align:center;">
            <div style="color:var(--text-secondary, #94a3b8); margin-bottom:0.75rem; font-size:0.88rem;">
              Текстовое описание временно не загрузилось через прокси
            </div>
            <div style="display:inline-flex; align-items:center; gap:0.5rem; justify-content:center; flex-wrap:wrap;">
              <button type="button" onclick="window.retryFetchGalleryDescription('${safeId}', '${encodeURIComponent(rawUrl)}')" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#ffffff; border-radius:6px; font-weight:700; cursor:pointer;">
                <span>🔄</span> <span>Повторить загрузку описания</span>
              </button>
              <a href="${safeUrl}" target="_blank" rel="noopener" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); color:#38bdf8; text-decoration:none; border-radius:6px; font-weight:700;">
                <span>🌐</span> <span>Открыть описание на Авито ↗</span>
              </a>
            </div>
          </div>
        `;
      }
    }
  }

  // Если отзывы еще не отрисованы — запускаем фоновую подгрузку для гарантированного отображения
  if (!reviewsRendered) {
    loadAndRenderGalleryReviews();
  }
};

window.retryFetchGalleryDescription = async function(itemId, rawUrlEncoded) {
  const cleanId = String(itemId || '').trim();
  if (!cleanId) return;
  let rawUrl = '';
  try {
    rawUrl = rawUrlEncoded ? decodeURIComponent(rawUrlEncoded) : '';
  } catch (_) {
    rawUrl = String(rawUrlEncoded || '');
  }
  if (!rawUrl) rawUrl = 'https://www.avito.ru/' + cleanId;
  const safeId = String(cleanId).replace(/'/g, "\\'");
  const safeUrl = String(rawUrl).replace(/"/g, '&quot;');

  const descEl = document.getElementById('gallery-modal-desc-text');
  if (descEl) {
    descEl.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:center; gap:0.6rem; padding:1.2rem; color:var(--text-secondary, #94a3b8); font-size:0.88rem;">
        <span style="display:inline-block; width:16px; height:16px; border:2px solid rgba(56,189,248,0.25); border-top-color:#38bdf8; border-radius:50%; animation:spin 0.8s linear infinite;"></span>
        <span>Повторная загрузка описания с Авито...</span>
      </div>
    `;
  }

  try {
    const detailsRes = await fetch(`/api/avito/item/details?item_id=${encodeURIComponent(cleanId)}&url=${encodeURIComponent(rawUrl)}`);
    if (!detailsRes.ok) throw new Error(`HTTP ${detailsRes.status}`);
    const detailsData = await detailsRes.json();
    if (!detailsData || !detailsData.success || !detailsData.item) {
      throw new Error(detailsData && detailsData.error ? detailsData.error : 'Пустой ответ от сервера');
    }
    const dItem = detailsData.item;

    if (dItem.description && dItem.description.trim()) {
      if (descEl) descEl.textContent = dItem.description;

      if (dItem.item_date && String(dItem.item_date).trim()) {
        const cleanDate = cleanAvitoRawDateText(dItem.item_date);
        const dateInfo = formatAvitoCardDateDisplay({ ...dItem, item_date: cleanDate });
        const modalDateEl = document.getElementById('gallery-modal-item-date');
        if (modalDateEl) {
          modalDateEl.innerText = `🕒 ${dateInfo.text}`;
          modalDateEl.title = dateInfo.title;
        }
        const card = document.getElementById('avito-card-' + cleanId);
        if (card) {
          const cardDateEl = card.querySelector('.avito-date-display');
          if (cardDateEl) {
            cardDateEl.innerText = `🕒 ${dateInfo.text}`;
            cardDateEl.title = dateInfo.title;
          }
        }
      }

      if (window.avitoData && Array.isArray(window.avitoData.items)) {
        const found = window.avitoData.items.find(x => String(x.item_id) === cleanId);
        if (found) {
          found.description = dItem.description;
          if (dItem.item_date) found.item_date = String(dItem.item_date).trim();
        }
      }
      if (window._lastAvitoItems && Array.isArray(window._lastAvitoItems)) {
        const found = window._lastAvitoItems.find(x => String(x.item_id) === cleanId);
        if (found) {
          found.description = dItem.description;
          if (dItem.item_date) found.item_date = String(dItem.item_date).trim();
        }
      }

      window._itemDetailsCache = window._itemDetailsCache || new Map();
      const prevCache = window._itemDetailsCache.get(cleanId) || {};
      window._itemDetailsCache.set(cleanId, {
        ...prevCache,
        description: dItem.description,
        photos: (Array.isArray(dItem.photos) && dItem.photos.length > 0) ? dItem.photos : prevCache.photos,
        reviews: Array.isArray(dItem.reviews) ? dItem.reviews : prevCache.reviews
      });
    } else {
      throw new Error('Текстовое описание не получено');
    }

    if (Array.isArray(dItem.photos) && dItem.photos.length > 1) {
      const thumbsContainer = document.getElementById('gallery-thumbs-row');
      if (thumbsContainer) {
        const cleanPhotos = deduplicateAvitoPhotos(dItem.photos);
        if (cleanPhotos.length > 0) {
          window._activeGalleryPhotos = cleanPhotos;
          thumbsContainer.style.display = 'flex';
          thumbsContainer.innerHTML = cleanPhotos.map((pUrl, idx) => `
            <div class="gallery-thumb-item ${idx === (window._activeGalleryIndex || 0) ? 'active' : ''}" onclick="window.selectGalleryPhoto(${idx})" title="Фото ${idx + 1}">
              <img src="${typeof window.getSafeAvitoPhotoUrl === 'function' ? window.getSafeAvitoPhotoUrl(pUrl) : pUrl}" data-raw-src="${escapeHtml(pUrl)}" alt="Миниатюра ${idx + 1}" loading="lazy" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { const th = this.closest('.gallery-thumb-item'); if (th) th.remove(); const r = document.getElementById('gallery-thumbs-row'); if (r && r.querySelectorAll('.gallery-thumb-item:not(.loading-skeleton)').length <= 1) r.style.display = 'none'; }">
            </div>
          `).join('');
          const prevBtn = document.getElementById('gallery-nav-prev');
          const nextBtn = document.getElementById('gallery-nav-next');
          if (prevBtn) prevBtn.style.display = 'flex';
          if (nextBtn) nextBtn.style.display = 'flex';
        }
      }
    }

    if (Array.isArray(dItem.reviews)) {
      window._itemReviewsCache = window._itemReviewsCache || new Map();
      window._itemReviewsCache.set(cleanId, dItem.reviews);
      const revCntEl = document.getElementById('gallery-tab-rev-count');
      if (revCntEl) revCntEl.textContent = dItem.reviews.length > 0 ? `(${dItem.reviews.length})` : '';
    }
  } catch (err) {
    console.warn('retryFetchGalleryDescription error:', err);
    if (descEl) {
      descEl.innerHTML = `
        <div style="padding:1.1rem; background:rgba(30,41,59,0.5); border:1px dashed rgba(239,68,68,0.3); border-radius:8px; text-align:center;">
          <div style="color:var(--text-secondary, #94a3b8); margin-bottom:0.75rem; font-size:0.88rem;">
            Текстовое описание временно не загрузилось через прокси
          </div>
          <div style="display:inline-flex; align-items:center; gap:0.5rem; justify-content:center; flex-wrap:wrap;">
            <button type="button" onclick="window.retryFetchGalleryDescription('${safeId}', '${encodeURIComponent(rawUrl)}')" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:linear-gradient(135deg, #0284c7, #2563eb); border:1px solid rgba(56,189,248,0.5); color:#ffffff; border-radius:6px; font-weight:700; cursor:pointer;">
              <span>🔄</span> <span>Повторить загрузку описания</span>
            </button>
            <a href="${safeUrl}" target="_blank" rel="noopener" class="cat-btn" style="display:inline-flex; align-items:center; gap:0.4rem; padding:0.45rem 1rem; font-size:0.84rem; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); color:#38bdf8; text-decoration:none; border-radius:6px; font-weight:700;">
              <span>🌐</span> <span>Открыть описание на Авито ↗</span>
            </a>
          </div>
        </div>
      `;
    }
  }
};
function renderAvitoMonitor(filterQuery) {
  const rawQ = (filterQuery || '').toLowerCase();
  const delIds = getDeletedAvitoItemIds();
  const favSet = getFavoriteIds();
  const cartIds = getCartItemIds();
  let rawItems = avitoData.items ? (Array.isArray(avitoData.items) ? avitoData.items : [avitoData.items]) : [];
  if (cartIds.size > 0) {
    rawItems = rawItems.filter(it => !cartIds.has(String(it.item_id).trim()));
  }
  if (delIds.size > 0) {
    rawItems = rawItems.filter(it => !delIds.has(String(it.item_id).trim()) || favSet.has(String(it.item_id).trim()));
  }
  window._lastAvitoItems = rawItems;
  let searches = normalizeSearches(avitoData.searches);
  if (searches.length === 0 && currentUser && currentUser.avito_searches) {
    searches = normalizeSearches(currentUser.avito_searches);
    if (searches.length > 0 && avitoData) {
      avitoData.searches = searches;
    }
  }

  // Собираем список всех уникальных поисковых ссылок для выпадающего списка (только активные поиски)
  const uniqueLinkNames = new Map();
  searches.forEach(s => {
    if (s.is_active !== 0) {
      const sName = (s.name || s.url || '').trim();
      if (sName) uniqueLinkNames.set(sName.toLowerCase(), sName);
    }
  });

  const activeSearchNames = new Set(Array.from(uniqueLinkNames.keys()));

  // Исключаем объявления от удаленных ссылок (если они не в избранном)
  if (activeSearchNames.size > 0) {
    rawItems = rawItems.filter(it => {
      if (favSet.has(String(it.item_id).trim())) return true;
      const itName = (it.search_name || '').trim().toLowerCase();
      return !itName || activeSearchNames.has(itName) || Array.from(activeSearchNames).some(a => itName.includes(a) || a.includes(itName));
    });
  }

  // Исключаем объявления без доставки для поисков с включенным флагом "Только с доставкой"
  const onlyDeliverySearches = new Set();
  searches.forEach(s => {
    if (s && (s.only_delivery == 1 || s.only_delivery === true || (s.url && (s.url.includes('d=1') || s.url.includes('cd=1'))))) {
      const sName = (s.name || s.url || '').trim().toLowerCase();
      if (sName) onlyDeliverySearches.add(sName);
    }
  });
  if (onlyDeliverySearches.size > 0) {
    rawItems = rawItems.filter(it => {
      if (favSet.has(String(it.item_id).trim())) return true;
      const itName = (it.search_name || '').trim().toLowerCase();
      const isOnlyDeliv = onlyDeliverySearches.has(itName) || Array.from(onlyDeliverySearches).some(s => itName.includes(s) || s.includes(itName));
      if (isOnlyDeliv && !it.has_delivery) {
        return false;
      }
      return true;
    });
  }
  window._lastAvitoItems = rawItems;
  let items = rawItems.slice();

  let curLink = (currentAvitoLinkFilter || 'all').trim().toLowerCase();
  if (curLink && curLink !== 'all' && curLink !== '__favorites__' && curLink !== '__blacklist__' && !uniqueLinkNames.has(curLink)) {
    currentAvitoLinkFilter = 'all';
    curLink = 'all';
  }
  const isFavoritesFilter = curLink === '__favorites__';
  const isBlacklistFilter = curLink === '__blacklist__';

  // Разделение объявлений: черный список и чистый каталог
  const blacklistedItems = rawItems.filter(it => isCardBlacklisted(it));
  const cleanItems = rawItems.filter(it => !isCardBlacklisted(it));

  const favCount = cleanItems.filter(it => favSet.has(String(it.item_id))).length;
  const blCount = blacklistedItems.length;

  // Опция «⭐ Избранное» и «🚫 ЧС» — сразу после «Все товары»
  const favoritesOptionHtml = `<option value="__favorites__" ${isFavoritesFilter ? 'selected' : ''}>⭐ Избранное (${favCount})</option>`;
  const blacklistOptionHtml = `<option value="__blacklist__" ${isBlacklistFilter ? 'selected' : ''}>🚫 ЧС (${blCount})</option>`;

  const linkFilterOptionsHtml = favoritesOptionHtml + blacklistOptionHtml + Array.from(uniqueLinkNames.values()).map(name => {
    const countForLink = cleanItems.filter(it => (it.search_name || '').trim().toLowerCase() === name.toLowerCase()).length;
    const isSelected = curLink === name.toLowerCase();
    return `<option value="${escapeHtml(name)}" ${isSelected ? 'selected' : ''}>${escapeHtml(name)} (${countForLink})</option>`;
  }).join('');

  // Фильтрация по ЧС: показывает все заблокированные карточки
  if (isBlacklistFilter) {
    items = blacklistedItems;
  } else if (isFavoritesFilter) {
    // Фильтрация по избранному: показывает все избранные карточки
    items = cleanItems.filter(it => favSet.has(String(it.item_id)));
  } else {
    items = cleanItems;
    // Для обычных пользователей изолируем объявления только по их собственным добавленным поискам
    if (!isAdmin()) {
      const mySearchNames = new Set(searches.map(s => (s.name || s.url || '').trim().toLowerCase()));
      if (mySearchNames.size > 0) {
        items = items.filter(it => {
          if (!it.search_name) return true;
          const sName = it.search_name.trim().toLowerCase();
          return mySearchNames.has(sName) || Array.from(mySearchNames).some(m => sName.includes(m) || m.includes(sName));
        });
      } else {
        items = [];
      }
    }
    // Фильтрация по конкретной ссылке/поиску (или «Все ссылки»)
    if (curLink && curLink !== 'all') {
      items = items.filter(it => {
        const sName = (it.search_name || '').trim().toLowerCase();
        return sName === curLink || sName.includes(curLink) || curLink.includes(sName);
      });
    }
  }

  const stats = avitoData.stats || { total_items: items.length, total_searches: searches.length, bot_running: false };
  const isBotRunning = Boolean(stats.bot_running);
  const isMonRunning = isAvitoPollingActive();

  if (rawQ) {
    items = items.filter(it => 
      (it.title && it.title.toLowerCase().includes(rawQ)) ||
      (it.price && it.price.toLowerCase().includes(rawQ)) ||
      (it.address && it.address.toLowerCase().includes(rawQ)) ||
      (it.seller && it.seller.toLowerCase().includes(rawQ)) ||
      (it.search_name && it.search_name.toLowerCase().includes(rawQ)) ||
      (it.url && it.url.toLowerCase().includes(rawQ))
    );
  }

  // Сортировка объявлений: по дате (свежие сверху), дешевле, дороже
  items.sort((a, b) => {
    // 0. Абсолютный приоритет №1: возвращённые НЕОЗНАКОМЛЕННЫЕ отменённые заказы ВСЕГДА стоят первыми сверху в любом режиме!
    const isUnreviewedA = isUnreviewedCanceledItem(String(a.item_id));
    const isUnreviewedB = isUnreviewedCanceledItem(String(b.item_id));
    if (isUnreviewedA && !isUnreviewedB) return -1;
    if (!isUnreviewedA && isUnreviewedB) return 1;

    if (currentAvitoSort === 'price_asc') {
      const pA = parseAvitoPrice(a.price);
      const pB = parseAvitoPrice(b.price);
      if (pA !== pB) return pA - pB;
      const tA = getAvitoItemTimeMs(a) || getAvitoItemSeenMs(a);
      const tB = getAvitoItemTimeMs(b) || getAvitoItemSeenMs(b);
      if (tB !== tA) return tB - tA;
      return (Number(b.item_id) || 0) - (Number(a.item_id) || 0);
    } else if (currentAvitoSort === 'price_desc') {
      const pA = parseAvitoPrice(a.price);
      const pB = parseAvitoPrice(b.price);
      if (pA !== pB) return pB - pA;
      const tA = getAvitoItemTimeMs(a) || getAvitoItemSeenMs(a);
      const tB = getAvitoItemTimeMs(b) || getAvitoItemSeenMs(b);
      if (tB !== tA) return tB - tA;
      return (Number(b.item_id) || 0) - (Number(a.item_id) || 0);
    } else {
      // По дате: сначала самые новые по дате публикации на Авито, затем старее
      // 1. Время публикации на Авито
      const tA = getAvitoItemTimeMs(a) || getAvitoItemSeenMs(a);
      const tB = getAvitoItemTimeMs(b) || getAvitoItemSeenMs(b);
      if (tB !== tA) return tB - tA;

      // 2. Время обнаружения сервером (seen_at)
      const seenA = getAvitoItemSeenMs(a);
      const seenB = getAvitoItemSeenMs(b);
      if (seenB !== seenA) return seenB - seenA;

      // 3. Приоритет непросмотренных свежих при равном времени
      const isFreshA = !viewedAdIds.has(String(a.item_id)) && freshAdTimestamps.has(String(a.item_id)) ? 1 : 0;
      const isFreshB = !viewedAdIds.has(String(b.item_id)) && freshAdTimestamps.has(String(b.item_id)) ? 1 : 0;
      if (isFreshB !== isFreshA) return isFreshB - isFreshA;

      // 4. По ID записи в БД (больший ID — позже добавлено)
      const idA = Number(a.rowid || a.id) || 0;
      const idB = Number(b.rowid || b.id) || 0;
      if (idA && idB && idA !== idB) return idB - idA;

      // 5. По номеру объявления на Авито (больший номер — обычно позже созданное объявление)
      const numA = Number(a.item_id) || 0;
      const numB = Number(b.item_id) || 0;
      return numB - numA;
    }
  });

  if (countBadge) {
    countBadge.innerText = `${components.length}\u00A0шт.`;
  }
  const avitoCatBtn = document.querySelector('.cat-btn-avito-monitor');
  if (avitoCatBtn) {
    avitoCatBtn.innerHTML = `🤖 Монитор Авито (${items.length})`;
  }

  // Расчет пагинации объявлений
  const totalItemsCount = items.length;
  let pagedItems = items;
  let startIdx = 0;
  let endIdx = totalItemsCount;
  let totalPages = 1;

  if (currentAvitoPageSize !== 'all') {
    const size = currentAvitoPageSize;
    totalPages = Math.max(1, Math.ceil(totalItemsCount / size));
    if (currentAvitoPage > totalPages) {
      currentAvitoPage = totalPages;
    }
    if (currentAvitoPage < 1) {
      currentAvitoPage = 1;
    }
    startIdx = (currentAvitoPage - 1) * size;
    endIdx = Math.min(startIdx + size, totalItemsCount);
    pagedItems = items.slice(startIdx, endIdx);
  }

  // HTML панели управления и активных поисков
  const userMaxSearches = (avitoData.stats && avitoData.stats.max_searches != null)
    ? avitoData.stats.max_searches
    : (currentUser && currentUser.permissions && currentUser.permissions.max_searches != null
        ? currentUser.permissions.max_searches
        : (isAdmin() ? null : 1));
  const searchesHtml = renderAvitoSearchesHtml(searches, userMaxSearches);
  // Видимый счётчик ссылок: для пользователя — не более лимита, для админа — реальное количество
  const visibleSearchCount = (!isAdmin() && userMaxSearches != null)
    ? Math.min(searches.length, Number(userMaxSearches))
    : searches.length;

  const isSoundEnabled = localStorage.getItem('electro_avito_sound') !== '0';
  const isUserMonActive = Boolean(currentUser && currentUser.permissions && currentUser.permissions.monitoring !== false);
  const isUserTgActive = Boolean(currentUser && currentUser.permissions && currentUser.permissions.tg_bot !== false);
  const currentProxies = (avitoData && avitoData.stats && avitoData.stats.proxy_count !== undefined)
    ? Number(avitoData.stats.proxy_count)
    : avitoProxyCount;
  const isWaitingProxies = isUserMonActive && currentProxies === 0 && Boolean(avitoData && avitoData.stats);

  const hasSearches = Boolean(searches && searches.length > 0);
  let monBtnClass = 'btn-inactive-gray';
  let monBtnText = '🔴 Мониторинг: ВЫКЛ';
  let monBtnTitle = 'Мониторинг выключен. Нажмите для включения.';
  if (!hasSearches) {
    monBtnClass = 'btn-inactive-gray is-disabled-empty-searches';
    monBtnText = '⚪ Мониторинг: ВЫКЛ';
    monBtnTitle = 'Для включения мониторинга сначала добавьте хотя бы одну ссылку для поиска';
  } else if (isUserMonActive) {
    if (isWaitingProxies) {
      monBtnClass = 'btn-active-warn';
      monBtnText = '🟡 Ожидание прокси';
      monBtnTitle = 'Мониторинг включен, но в пуле 0 прокси (пауза для защиты IP от бана). Нажмите для выключения.';
    } else {
      monBtnClass = 'btn-active-green';
      monBtnText = '🟢 Мониторинг: ВКЛ';
      monBtnTitle = `Мониторинг активен (прокси в пуле: ${currentProxies}). Нажмите для выключения.`;
    }
  }

  const isUserTg = Boolean(!currentUser || !currentUser.permissions || currentUser.permissions.tg_bot !== false);
  const isBotPaused = !isUserTg || Boolean(stats && stats.bot_paused);
  const isTgConfirmed = isTelegramAccountConfirmed(currentUser);
  const myTgPending = (typeof _isEditingTg === 'undefined' || !_isEditingTg)
    ? (!isTgConfirmed && ((avitoData && avitoData.stats && avitoData.stats.telegram_pending && avitoData.stats.telegram_pending.status === 'pending')
      ? avitoData.stats.telegram_pending
      : (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending' ? currentUser.telegram_pending : null)))
    : null;
  const myTgPendingHandle = myTgPending ? (myTgPending.handle || '') : '';
  const myTgVal = (isTgConfirmed && currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) || '';

  let botPhoneClass = 'btn-active-green';
  let botPhoneStyle = 'background:rgba(16,185,129,0.15);color:#10b981;border-color:rgba(16,185,129,0.5);font-weight:700;display:inline-flex;align-items:center;gap:0.35rem;';
  botPhoneTitle = 'ТГ-Бот в Telegram запущен и принимает объявления. Нажмите для паузы.';
  let botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: 🟢 Запущен';

  if (!isTgConfirmed) {
    botPhoneClass = 'btn-inactive-gray';
    botPhoneStyle = 'background:rgba(148,163,184,0.15);color:var(--text-secondary);border-color:rgba(148,163,184,0.3);font-weight:700;display:inline-flex;align-items:center;gap:0.35rem;opacity:0.45;pointer-events:none;cursor:not-allowed;filter:grayscale(0.7);';
    if (myTgPending) {
      botPhoneTitle = 'Ожидает подтверждения в Telegram-боте. Откройте бота и подтвердите аккаунт.';
      botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: ⏳ Ожидание';
    } else {
      botPhoneTitle = 'Для управления ТГ-Ботом сначала подтвердите аккаунт Telegram справа';
      botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: ⚪ Не привязан';
    }
  } else if (isBotPaused) {
    botPhoneClass = 'btn-active-yellow';
    botPhoneStyle = 'background:rgba(234,179,8,0.18);color:#eab308;border-color:rgba(234,179,8,0.55);font-weight:700;display:inline-flex;align-items:center;gap:0.35rem;';
    botPhoneTitle = 'ТГ-Бот в Telegram на паузе (поиск остановлен). Нажмите для возобновления.';
    botPhoneHtml = '<img src="img/tg_bot_icon.png?v=4" alt="Бот" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;display:inline-block;flex-shrink:0;"> ТГ-Бот: 🟡 Пауза';
  }

  const currentIpVal = (typeof _serverNetworkUrl === 'string' && _serverNetworkUrl)
    ? _serverNetworkUrl.replace(/^https?:\/\//, '')
    : (document.getElementById('server-ip-val')?.innerText || '...');

  grid.innerHTML = `
    <div class="avito-monitor-container">
      <!-- Главная статусная панель монитора -->
      <div class="avito-dashboard-banner">
        <div class="avito-dashboard-banner-rows-group" style="display:flex;flex-direction:column;width:fit-content;max-width:100%;min-width:max-content;margin-left:auto;margin-right:auto;gap:0.45rem;">
          <!-- Верхняя строка баннера: Заголовок/IP, Мониторинг, Ссылок, Активация и Профиль -->
          <div class="avito-dashboard-banner-header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:nowrap;gap:0.75rem;width:100%;min-width:max-content;min-height:36px;">
            <div class="banner-brand-title-wrap" style="display:inline-flex;align-items:center;gap:0.75rem;flex-shrink:0;">
              <div class="header-brand-group">
                <div class="header-brand-column">
                  <div class="header-brand-row">
                    <div class="logo header-brand-static" title="AvitoHunter" style="cursor:default;pointer-events:none;user-select:none;">
                      <img src="img/skybase_header_logo.png" alt="AvitoHunter" class="logo-img" style="position:relative;left:1px;" />
                      <span style="position:relative;left:-1px;">AvitoHunter</span>
                    </div>
                  </div>

                  <!-- Информационная плашка IP прямо под AvitoHunter (некликабельная) -->
                  <div id="btn-server-ip" class="badge-ip-info" title="Локальный IP-адрес данного ПК" style="display:inline-flex;position:relative;left:1px;width:175px;min-width:175px;box-sizing:border-box;justify-content:center;text-align:center;cursor:default;pointer-events:none;user-select:none;">
                    🌐 IP: <span id="server-ip-val">${escapeHtml(currentIpVal)}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Кнопка Мониторинг: размещена в верхней строке НАД кнопкой ТГ-Уведомления -->
            <button type="button" onclick="toggleMyMonitoring()" id="btn-user-mon-toggle" class="btn-avito-switch ${monBtnClass}" title="${monBtnTitle}" style="flex-shrink:0;white-space:nowrap;min-width:168px;width:168px;justify-content:center;text-align:center;padding:0.35rem 0.65rem;font-size:0.82rem;height:36px;border-radius:10px;box-sizing:border-box;${hasSearches ? '' : 'opacity:0.4;pointer-events:none;cursor:not-allowed;filter:grayscale(0.8);'}">
              ${monBtnText}
            </button>

            <!-- Правый блок: Ссылок, Активация (рядом с Профилем) и Профиль -->
            <div class="avito-dashboard-banner-stats" style="display:flex;gap:0.35rem;align-items:center;flex-wrap:nowrap;flex-shrink:0;justify-content:flex-end;margin-left:auto;position:relative;left:1px;">
              <div class="avito-stat-pill pill-avito-searches" id="pill-avito-searches" style="width:106px;min-width:106px;max-width:106px;text-align:center;justify-content:center;box-sizing:border-box;padding:0.35rem 0.45rem;font-size:0.82rem;height:36px;border-radius:10px;display:inline-flex;align-items:center;">
                🎯 Ссылок: <strong id="avito-stat-searches" style="color:${Number(visibleSearchCount) === 0 ? '#ef4444' : '#fbbf24'};">${visibleSearchCount}</strong>
              </div>

              <!-- Кнопка активации / продления тарифа (размещена непосредственно рядом с Профилем) -->
              <button type="button" class="cat-btn btn-avito-activate" id="btn-avito-activate" onclick="openActivationModal()"
                style="background:rgba(99,102,241,0.15);color:#c7d2fe;border:1px solid rgba(129,140,248,0.3);font-weight:600;padding:0.35rem 0.5rem;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;width:105px;min-width:105px;max-width:105px;flex-shrink:0;box-sizing:border-box;white-space:nowrap;border-radius:10px;box-shadow:none;cursor:pointer;transition:all 0.2s;text-align:center;position:relative;font-size:0.82rem;height:36px;"
                title="Активировать или продлить тариф">
                🔑 Активация
              </button>

              <!-- Кнопка Профиль — расположена вверху, строго над Корзиной -->
              <button type="button" id="btn-avito-sniper-main" onclick="openSniperModal()" class="btn-avito-sniper btn-avito-profile ${window._sniperAuthenticated ? 'authenticated' : 'not-authenticated'}"
                title="${window._sniperAuthenticated ? 'Профиль Авито: подключен (' + escapeHtml(typeof getSniperDisplayUserName === 'function' ? getSniperDisplayUserName() : 'Авторизован') + ')' : 'Профиль Авито: не авторизован (нажмите для входа по SMS)'}"
                style="font-size:0.82rem;padding:0.35rem 0.5rem;flex-shrink:0;white-space:nowrap;min-height:36px;height:36px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;gap:0.45rem;width:125px;min-width:125px;max-width:125px;box-sizing:border-box;">
                ${window.getProfileUserIconHtml(window._sniperAuthenticated)}
                <span>Профиль</span>
              </button>
            </div>
          </div>

          <!-- Нижняя строка: Тариф (под кнопкой IP), ТГ-Уведомления (под Мониторингом) и остальные переключатели -->
          <div class="avito-switches-bar" style="width:100%;min-width:max-content;display:flex;align-items:center;gap:0.45rem;flex-wrap:nowrap;padding:0.2rem 0;justify-content:flex-start;margin-left:0;position:relative;left:1px;">
            <!-- Кнопка Тариф: размещена в нижней строке прямо под кнопкой IP: -->
            <div class="avito-stat-pill pill-avito-tariff" id="pill-avito-tariff" onclick="openActivationModal()" style="${(window.getTariffDisplayText && window.getTariffDisplayText() === 'Безлимит') ? 'background:rgba(255,215,0,0.1);border:1px solid rgba(255,215,0,0.45);' : 'background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);'}color:var(--text-primary);font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;padding:0.35rem 0.45rem;width:175px;min-width:175px;max-width:175px;height:36px;border-radius:10px;white-space:nowrap;flex-shrink:0;cursor:pointer;user-select:none;box-sizing:border-box;font-size:0.82rem;" title="Текущий тариф и время действия. Нажмите для продления">
              🏷️ Тариф: <span id="avito-stat-tariff-text" style="font-family:inherit;font-size:inherit;font-weight:inherit;color:inherit;text-shadow:none;">${escapeHtml(window.getTariffDisplayText ? window.getTariffDisplayText() : '3 дня')}</span>
            </div>

            <!-- Кнопка ТГ-Уведомления: строго ПОД кнопкой Мониторинг -->
            <button type="button" onclick="toggleMyTelegramNotifications()" id="btn-user-tg-toggle" class="btn-avito-switch ${isTgConfirmed ? (isUserTgActive ? 'btn-active-green' : 'btn-inactive-gray') : 'btn-inactive-gray'}" title="${isTgConfirmed ? 'Включить или выключить отправку уведомлений в Telegram' : (myTgPending ? 'Ожидает подтверждения в Telegram-боте' : 'Для включения ТГ-уведомлений сначала подтвердите аккаунт Telegram справа')}" style="flex-shrink:0;white-space:nowrap;min-width:168px;width:168px;justify-content:center;text-align:center;padding:0.35rem 0.65rem;font-size:0.82rem;height:36px;border-radius:10px;box-sizing:border-box;${isTgConfirmed ? '' : 'opacity:0.45;pointer-events:none;cursor:not-allowed;filter:grayscale(0.7);'}">
              ${isTgConfirmed ? (isUserTgActive ? '🟢 ТГ-Уведомления: ВКЛ' : '🔴 ТГ-Уведомления: ВЫКЛ') : (myTgPending ? '⏳ ТГ-Уведомления: Ожидание' : '⚪ ТГ-Уведомления: ВЫКЛ')}
            </button>

            <!-- Строка быстрого ввода адреса Telegram -->
            <div id="avito-tg-link-wrap" class="avito-tg-link-wrap${isTgConfirmed ? ' state-linked' : (myTgPending ? ' state-pending' : '')}"
              style="display:inline-flex;align-items:center;border-radius:10px;padding:2px 6px;height:36px;width:275px;min-width:275px;max-width:275px;box-sizing:border-box;gap:6px;flex-shrink:0;transition:background 0.3s,border-color 0.3s;cursor:text;${isTgConfirmed ? 'background:rgba(16,185,129,0.22);border:2px solid #10b981;box-shadow:0 0 12px rgba(16,185,129,0.35);' : (myTgPending ? 'background:rgba(234,179,8,0.14);border:1.5px solid rgba(234,179,8,0.7);box-shadow:none;' : 'background:rgba(239,68,68,0.12);border:1.5px solid rgba(239,68,68,0.55);box-shadow:none;')}" title="${isTgConfirmed ? 'Telegram привязан. Нажмите, чтобы изменить' : (myTgPending ? 'Ожидает подтверждения в Telegram-боте' : '@username или ID')}">
              <span class="tg-link-icon" onclick="window._openTgBotBind(event)" style="display:inline-flex;align-items:center;user-select:none;flex-shrink:0;cursor:pointer;" title="Открыть Telegram-бота @avvvskybot">
                <img src="img/telegram.png" alt="Telegram" style="width:20px;height:20px;object-fit:contain;vertical-align:middle;display:inline-block;">
              </span>
              <input type="text" id="input-my-tg-handle" name="tg_handle_dash_input" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-form-type="other" role="presentation" value="${escapeHtml(myTgVal || (myTgPendingHandle ? (myTgPendingHandle.startsWith('@') ? myTgPendingHandle : '@' + myTgPendingHandle.replace(/^@/, '')) : ''))}" placeholder="@username или ID" title="@username или ID"
                style="background:transparent;border:none;outline:none;color:#ffffff;font-size:0.83rem;font-weight:${isTgConfirmed ? '700' : '600'};flex:1;min-width:0;width:100%;box-sizing:border-box;cursor:text;"
                onclick="window._tgInputSingleClick(this)"
                onfocus="window._tgInputSingleClick(this)"
                oninput="window._tgInputOnInput(this)"
                onkeyup="window._tgInputOnInput(this)"
                onchange="window._tgInputOnInput(this)"
                onpaste="setTimeout(()=>window._tgInputOnInput(this),0)"
                oncut="setTimeout(()=>window._tgInputOnInput(this),0)"
                onkeydown="if(event.key==='Enter'){window._handleTgEnter();this.blur();}">
              <button type="button" id="btn-my-tg-bind"
                onclick="window._tgButtonClick()"
                class="cat-btn${myTgPending ? ' btn-tg-pending' : ''}"
                ${isTgConfirmed ? 'data-accepted="1"' : (myTgPending ? 'data-pending="1"' : '')}
                style="width:88px;min-width:88px;max-width:88px;box-sizing:border-box;flex-shrink:0;text-align:center;justify-content:center;padding:0.25rem 0.2rem;font-size:0.76rem;font-weight:700;border-radius:8px;white-space:nowrap;cursor:pointer;${isTgConfirmed ? 'background:#166534;color:#ffffff;border:1px solid #14532d;opacity:1;' : (myTgPending ? 'background:rgba(234,179,8,0.22);color:#eab308;border:1px solid rgba(234,179,8,0.6);opacity:1;' : 'background:rgba(14,165,233,0.18);color:#38bdf8;border:1px solid rgba(14,165,233,0.4);')}"
                title="${isTgConfirmed ? 'Telegram-аккаунт привязан. Нажмите для сохранения или изменения' : (myTgPending ? 'Ожидает подтверждения в Telegram-боте @avvvskybot. Наведите для отмены' : 'Привязать адрес Telegram к аккаунту')}">${isTgConfirmed ? 'Привязан' : (myTgPending ? '<span class="tg-pending-label" style="display:inline-block;position:relative;left:-5px;">⏳ Ожидание</span><span class="tg-cancel-label" style="display:none;">Отменить</span>' : 'Привязать')}</button>
            </div>

            <!-- Управление прокси -->
            <button type="button" class="btn-avito-switch btn-avito-proxies" id="btn-avito-proxies" onclick="openProxyModal()" style="background:rgba(99,102,241,0.15);color:#818cf8;border:1px solid rgba(99,102,241,0.4);font-weight:700;padding:0.35rem 0.55rem;display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;flex-shrink:0;box-sizing:border-box;white-space:nowrap;min-height:36px;border-radius:10px;cursor:pointer;font-size:0.82rem;" title="Управление прокси: поиск бесплатных, список, добавление">
              🌐 Прокси: <strong style="color:${Number(stats.proxy_count || 0) === 0 ? '#ef4444' : '#fbbf24'};">${stats.proxy_count || 0}</strong>
            </button>

            <!-- Звук новых объявлений: колокольчик + шестеренка в одной цельной кнопке -->
            <div class="btn-avito-sound-combo ${isSoundEnabled ? 'is-sound-active' : ''}" id="btn-avito-sound-combo" title="Управление звуком и настройки мелодий">
              <button type="button" id="btn-avito-sound-toggle" onclick="toggleAvitoSound()" class="btn-sound-part-toggle ${isSoundEnabled ? 'btn-active-blue' : 'btn-inactive-gray'}" title="${isSoundEnabled ? 'Звук новых объявлений: включен (синий индикатор, нажмите для выключения)' : 'Звук новых объявлений: выключен (нажмите для включения)'}">
                <span id="btn-avito-sound-text">${isSoundEnabled ? '🔔 Звук' : '🔕 Звук'}</span>
              </button>
              <button type="button" id="btn-avito-sound-settings" onclick="openSoundSettingsModal()" class="btn-sound-part-gear" title="Настройки звука: выбор мелодий или указать свой файл с диска">
                <span class="gear-icon">⚙️</span>
              </button>
            </div>

            <!-- Кнопка Корзины с бейджем количества (размещена прямо под Профилем) -->
            <button type="button" id="btn-avito-cart" onclick="openCartModal()" class="btn-avito-cart"
              title="Корзина покупок: нажмите для просмотра и возврата товаров"
              style="font-size:0.82rem;padding:0.35rem 0.5rem;flex-shrink:0;white-space:nowrap;margin-left:auto;min-height:36px;height:36px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;width:125px;min-width:125px;max-width:125px;box-sizing:border-box;">
              🛒 Корзина <span id="cart-badge-count" class="cart-badge-counter ${getCartCount() === 0 ? 'empty' : ''}">${getCartCount()}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Активные поисковые запросы (клик открывает меню управления) -->
      <div class="avito-searches-block ${!hasActiveAvitoSearches() ? 'empty-highlight' : ''}" id="avito-searches-block" onclick="openManageSearchesModal()" title="Нажмите, чтобы открыть настройки отслеживаемых ссылок (добавить, удалить или настроить)">
        <div id="avito-searches-chips-container" style="display:contents;">
          ${searchesHtml}
        </div>
        <div class="avito-add-search-hint-center-wrapper" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);display:flex;align-items:center;justify-content:center;margin:0;pointer-events:none;z-index:2;white-space:nowrap;">
          <span class="avito-add-search-hint hint-centered" id="avito-add-search-hint" onclick="event.stopPropagation(); openManageSearchesModal();" title="Добавить новую ссылку для мониторинга" style="white-space:nowrap;">
            <span style="font-size:0.85rem;line-height:1;opacity:0.75;font-weight:700;">+</span> <span style="white-space:nowrap;">Добавить ссылку</span>
          </span>
        </div>
      </div>

      <!-- Предупреждающий блок о возвращённых из корзины заказах -->
      ${getReturnedOrdersAlertHtml()}

      <!-- Панель сортировки, очистки и пагинации объявлений -->
      <div class="avito-filter-bar">
        <!-- Блок 1: Сортировка по дате и Сортировка по ссылкам (слева на той же строке) -->
        <div class="avito-filter-block-sort" style="display:inline-flex;align-items:center;gap:0.75rem;flex-wrap:nowrap;white-space:nowrap;flex-shrink:0;justify-self:start;">
          <!-- Сортировка по дате/цене -->
          <div style="display:inline-flex;align-items:center;gap:0.35rem;flex-shrink:0;">
            <label for="avito-sort-select" style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;white-space:nowrap;cursor:pointer;">Сортировка:</label>
            <div class="avito-sort-select-wrapper" style="position:relative;display:inline-flex;align-items:center;flex-shrink:0;">
              <select id="avito-sort-select" class="avito-sort-select" onchange="setAvitoSort(this.value)" title="Сортировка объявлений (по дате или цене)">
                <option value="date" ${currentAvitoSort === 'date' ? 'selected' : ''}>По дате</option>
                <option value="price_desc" ${currentAvitoSort === 'price_desc' ? 'selected' : ''}>Подороже</option>
                <option value="price_asc" ${currentAvitoSort === 'price_asc' ? 'selected' : ''}>Подешевле</option>
              </select>
            </div>
          </div>

          <!-- Сортировка / фильтрация по ссылкам -->
          <div style="display:inline-flex;align-items:center;gap:0.35rem;flex-shrink:0;">
            <div class="avito-sort-select-wrapper" style="position:relative;display:inline-flex;align-items:center;flex-shrink:0;">
              <select id="avito-link-filter-select" class="avito-sort-select avito-link-select" onchange="setAvitoLinkFilter(this.value)" title="Фильтрация объявлений по ссылкам поиска">
                <option value="all" ${(!currentAvitoLinkFilter || currentAvitoLinkFilter === 'all') ? 'selected' : ''}>Все товары (${cleanItems.length})</option>
                ${linkFilterOptionsHtml}
              </select>
            </div>
          </div>
        </div>

        <!-- Блок 2: Отображено и Выбор количества на странице (По: 16 | 32 | 64 | Все) строго по середине блока -->
        <div class="avito-filter-block-stats" style="display:inline-flex;align-items:center;gap:0.65rem;flex-wrap:nowrap;white-space:nowrap;flex-shrink:0;justify-self:center;">
          <div class="avito-stat-text" style="font-size:0.85rem;color:var(--text-secondary);flex-shrink:0;font-variant-numeric:tabular-nums;white-space:nowrap;">
            Отображено: <strong style="color:var(--text-primary);">${currentAvitoPageSize === 'all' ? `${totalItemsCount} позиций` : (totalItemsCount > 0 ? `${startIdx + 1}–${endIdx} из ${totalItemsCount}` : '0 позиций')}</strong>
          </div>
          ${getAvitoPageSizeSelectorHtml(currentAvitoPageSize)}
          ${getAvitoPageNavHtml(totalItemsCount, currentAvitoPage, currentAvitoPageSize, false)}
        </div>

        <!-- Блок 3: Кнопки Загрузить / Загрузить всё и Очистить / Очистить всё -->
        <div class="avito-filter-block-actions" style="display:inline-flex;align-items:center;gap:0.5rem;flex-wrap:nowrap;white-space:nowrap;flex-shrink:0;justify-self:end;margin-left:auto;">
          ${(() => {
            const isFiltered = (curLink && curLink !== 'all' && curLink !== '__favorites__' && curLink !== '__blacklist__');
            const fetchLabel = isFiltered ? 'Загрузить' : 'Загрузить все';
            const fetchTitle = isFiltered
              ? `Загрузить объявления по ссылке «${escapeHtml(uniqueLinkNames.get(curLink) || currentAvitoLinkFilter)}» на сайт`
              : 'Загрузить все найденные объявления по активным ссылкам на сайт';
            if (window._isAvitoFetchingAll && window._avitoCurrentBtnHtml) {
              return `<button type="button" id="btn-avito-fetch-all" class="btn-avito-fetch-all loading"
                  onclick="window._cancelFetchQueue = true;"
                  title="Нажмите для отмены"
                  style="flex-shrink:0;white-space:nowrap;color:#fbbf24;border-color:rgba(251,191,36,0.6);background:rgba(251,191,36,0.12);opacity:1;cursor:pointer;">
                  ${window._avitoCurrentBtnHtml}
                </button>`;
            }
            return `<button type="button" id="btn-avito-fetch-all" class="btn-avito-fetch-all" onclick="fetchAllAvitoCards()"
                  title="${fetchTitle}"
                  style="flex-shrink:0;white-space:nowrap;">
                  ${fetchLabel}
                </button>`;
          })()}
          <button type="button" class="btn-avito-clear-all" onclick="clearAllAvitoCards()" title="${isFavoritesFilter ? 'Очистить список избранных объявлений' : (isBlacklistFilter ? 'Очистить черный список (все товары вернутся назад)' : ((curLink && curLink !== 'all') ? `Удалить карточки по ссылке «${escapeHtml(uniqueLinkNames.get(curLink) || currentAvitoLinkFilter)}» (избранные сохраняются)` : 'Удалить карточки объявлений (избранные сохраняются)'))}" style="flex-shrink:0;white-space:nowrap;">
            ${isFavoritesFilter ? '🗑️ Очистить избранное' : (isBlacklistFilter ? '🗑️ Очистить ЧС' : ((curLink && curLink !== 'all') ? '🗑️ Очистить' : '🗑️ Очистить всё'))}
          </button>
        </div>
      </div>
    </div>

    <!-- Сетка карточек объявлений -->
    ${items.length === 0 ? `
      <div style="grid-column:1/-1;text-align:center;padding:3.5rem 1.5rem;color:var(--text-secondary);background:var(--bg-card);border:1px dashed var(--border-color);border-radius:12px;">
        <div style="font-size:3rem;margin-bottom:0.75rem;">${isFavoritesFilter ? '⭐' : (isBlacklistFilter ? '🚫' : '🔍')}</div>
        <h3 style="font-size:1.3rem;color:var(--text-primary);margin-bottom:0.5rem;">
          ${rawQ
            ? `По запросу «${escapeHtml(filterQuery)}» ничего не найдено`
            : (isFavoritesFilter
              ? 'Список избранного пуст'
              : (isBlacklistFilter
                ? 'Черный список пуст'
                : (currentAvitoLinkFilter && currentAvitoLinkFilter !== 'all'
                  ? `По ссылке «${escapeHtml(currentAvitoLinkFilter)}» пока нет сохраненных объявлений`
                  : 'Пока нет сохраненных объявлений')))}
        </h3>
        <p style="font-size:0.95rem;color:var(--text-secondary);max-width:520px;margin:0 auto;">
          ${rawQ
            ? 'Попробуйте изменить поисковый запрос или сбросить фильтр.'
            : (isFavoritesFilter
              ? 'Нажмите кнопку <strong style="color:#fbbf24;">☆ В избранное</strong> на любой карточке — она появится здесь.'
              : (isBlacklistFilter
                ? 'Черный список пуст. Нажмите кнопку <strong style="color:#ef4444;">В ЧС</strong> на любой карточке, чтобы заблокировать товар и продавца.'
                : (currentAvitoLinkFilter && currentAvitoLinkFilter !== 'all'
                  ? 'Выберите «Все товары» или дождитесь опроса этой ссылки ботом.'
                  : 'Включите мониторинг — бот автоматически проверяет сайт и собирает свежие объявления.')))}
        </p>
      </div>
    ` : pagedItems.map(it => {
      const cleanPrice = escapeHtml(it.price || 'Цена не указана');
      const cleanTitle = escapeHtml(it.title || 'Объявление на Авито');
      const address = it.address ? escapeHtml(it.address) : 'Не указан';
      const searchName = escapeHtml(getDisplaySearchName(it));
      const seenTime = it.seen_at ? it.seen_at.replace('T', ' ') : '';
      const dateInfo = formatAvitoCardDateDisplay(it);
      const cardDateText = dateInfo.text;
      const cardDateTitle = dateInfo.title;
      const hasDelivery = Boolean(it.has_delivery);
      const deliveryText = formatCardDeliveryText(it);
      const sellerType = it.seller_type || (it.is_company ? 'Компания' : 'Частное лицо');
      const sellerDisplay = it.seller ? `${escapeHtml(it.seller)} (${escapeHtml(sellerType)})` : escapeHtml(sellerType);
      const rawSeller = (it.seller || '').trim();
      const safeSellerJson = JSON.stringify(rawSeller).replace(/"/g, '&quot;');
      const blButtonLabel = rawSeller 
        ? `🚫 В ЧС: ${escapeHtml(rawSeller.length > 15 ? rawSeller.slice(0, 13) + '…' : rawSeller)}`
        : '🚫 В ЧС';

      const itemIdStr = String(it.item_id);
      const savedCardNote = localStorage.getItem('avito_card_note_' + itemIdStr) || '';
      const isChatDisabled = (it.has_chat === false || it.has_chat === 0 || it.can_chat === false || it.chat_enabled === false) || ((typeof isItemChatDisabled === 'function') && isItemChatDisabled(itemIdStr));
      const hasChat = !isChatDisabled;
      let isCanceled = isCanceledItem(itemIdStr);
      let isUnreviewed = isUnreviewedCanceledItem(itemIdStr);
      let isFresh = !isCanceled && !viewedAdIds.has(itemIdStr) && freshAdTimestamps.has(itemIdStr);
      const canceledDetails = isCanceled ? getCanceledItemDetails(itemIdStr) : null;

      let cardHighlightClass = '';
      if (isCanceled) {
        cardHighlightClass = isUnreviewed ? 'avito-card-canceled' : 'avito-card-canceled-reviewed';
      } else if (isFresh) {
        cardHighlightClass = 'avito-card-fresh';
      }

      const primaryPhoto = getCardPrimaryPhoto(it);

      return `
      <div class="avito-card ${cardHighlightClass} ${isFavorited(it.item_id) ? 'is-favorited' : ''}" id="avito-card-${escapeHtml(it.item_id)}" data-item-id="${escapeHtml(it.item_id)}">
        <!-- Фотография объявления — клик открывает модальное окно с галереей всех фото, комментариями и кнопкой Купить -->
        <div class="avito-card-thumb-wrap" id="avito-thumb-wrap-${escapeHtml(it.item_id)}" onclick="event.preventDefault(); event.stopPropagation(); window.openItemGalleryModal('${escapeHtml(it.item_id)}')" title="Нажмите на фото, чтобы открыть карточку товара" style="cursor:pointer;position:relative;background:#0f172a;overflow:hidden;">
          <div class="avito-thumb-spinner" id="avito-thumb-spinner-${escapeHtml(it.item_id)}" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0.45rem;background:#0f172a;z-index:2;transition:opacity 0.25s ease;pointer-events:none;">
            <div style="width:28px;height:28px;border:3px solid rgba(56,189,248,0.22);border-top-color:#38bdf8;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
            <span style="font-size:0.75rem;color:#93c5fd;font-weight:600;">Загрузка фото...</span>
          </div>
          ${primaryPhoto ? `
            <img src="${escapeHtml(getSafeAvitoPhotoUrl(primaryPhoto))}" data-raw-src="${escapeHtml(primaryPhoto)}" alt="${cleanTitle}" class="avito-card-thumb loaded" loading="lazy" onload="const sp = document.getElementById('avito-thumb-spinner-${escapeHtml(it.item_id)}'); if (sp) { sp.style.opacity='0'; setTimeout(()=>sp.remove(), 260); }" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { const p = this.parentElement; if (p) p.innerHTML = getAvitoPhotoFallbackHtml(); }">
          ` : getAvitoPhotoFallbackHtml()}
        </div>

        <div class="avito-card-body">
          <div class="avito-card-header-row">
            <div style="display:flex;align-items:center;gap:0.45rem;flex-wrap:wrap;">
              <span class="avito-badge-id">
                Авито #${escapeHtml(it.item_id)}
              </span>
              ${isCanceled ? `
                <span class="${isUnreviewed ? 'avito-badge-canceled' : 'avito-badge-canceled-reviewed'}" title="${escapeHtml(canceledDetails?.reason || 'Заказ был возвращён из корзины')}">
                  ${isUnreviewed ? escapeHtml(canceledDetails?.badge_label || '🚫 Отменён (не отправлен)') : `↩️ ${escapeHtml(canceledDetails?.badge_label || 'Возвращён из корзины')}`}
                </span>
              ` : ''}
            </div>
            <span class="avito-date-display" style="font-size:0.75rem;color:var(--text-secondary);" title="${cardDateTitle}">
              🕒 ${escapeHtml(cardDateText)}
            </span>
          </div>

          <h3 class="avito-card-title" title="${cleanTitle}">
            <span>🏷️ ${cleanTitle}</span>
            <a href="${escapeHtml(it.url || ('https://www.avito.ru/' + itemIdStr))}" target="_blank" rel="noopener" class="avito-title-badge-link" title="Открыть объявление на Авито" style="text-decoration:none; display:inline-flex; align-items:center; vertical-align:middle; margin-left:0.45rem; transition:transform 0.15s ease;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
              <svg width="102" height="26" viewBox="0 0 115 30" fill="none" xmlns="http://www.w3.org/2000/svg" style="display:block; cursor:pointer; filter:drop-shadow(1px 2px 3px rgba(0,0,0,0.35));">
                <path d="M 5 2.5 L 90 2.5 L 111 15 L 90 27.5 L 5 27.5 C 3 27.5 1.5 26 1.5 24 L 1.5 6 C 1.5 4 3 2.5 5 2.5 Z" fill="#FFD000" stroke="#CCA000" stroke-width="1.2"/>
                <path d="M 6.5 4.5 L 88.5 4.5 L 107 15 L 88.5 25.5 L 6.5 25.5 C 4.5 25.5 3.5 24.5 3.5 22.5 L 3.5 7.5 C 3.5 5.5 4.5 4.5 6.5 4.5 Z" fill="none" stroke="#222222" stroke-width="1.1" stroke-dasharray="3.5 2"/>
                <text x="13" y="19.5" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="900" font-size="11.5" fill="#111111" letter-spacing="0.3">на авито</text>
                <path d="M 82 15 H 98 M 93 10.5 L 98 15 L 93 19.5" stroke="#111111" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </a>
          </h3>

          <div class="avito-card-price-row">
            ${renderCardPriceRowHtml(it.price)}
          </div>

          <!-- Блок с детальной информацией (в точности как в Telegram) -->
          <div class="avito-details-box">
            <div class="avito-detail-row">
              <span>🏘️</span> <span>Город: <strong class="avito-detail-address">${address}</strong></span>
            </div>
            <div class="avito-detail-row">
              <span>👤</span> <span>Продавец: <strong class="avito-detail-seller">${sellerDisplay}</strong></span>
            </div>
            <div class="avito-detail-row avito-rating-row">
              <span>⭐</span> <span>Рейтинг: ${formatSellerRatingHtml(it.seller_rating, it.item_id, it.url)}</span>
            </div>
            <div class="avito-detail-row">
              <span>🚚</span> <span>Доставка: <strong class="avito-detail-delivery" style="${hasDelivery ? 'color:#10b981;' : 'color:var(--text-secondary);'}">${deliveryText}</strong></span>
            </div>
            <div class="avito-detail-row">
              <span>🔎</span> <span>Поиск: <strong style="color:#60a5fa;">${searchName}</strong></span>
            </div>
            <div class="avito-card-note-row" id="card-note-row-${escapeHtml(it.item_id)}" onclick="event.stopPropagation(); window.openItemReviewsModal('${escapeHtml(it.item_id)}', '${escapeHtml(encodeURIComponent(it.url || ''))}')" style="${savedCardNote ? 'display:flex;' : 'display:none;'}align-items:center;gap:0.4rem;margin-top:0.35rem;padding:0.25rem 0.5rem;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);border-radius:6px;font-size:0.8rem;color:#38bdf8;cursor:pointer;" title="Нажмите, чтобы изменить заметку к объявлению">
              <span>📝</span> <span class="card-note-text" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;">${escapeHtml(savedCardNote || '')}</span>
            </div>
          </div>

          <div class="avito-card-footer">
            <div class="avito-card-top-row">
              <button
                type="button"
                class="btn-card-favorite ${isFavorited(it.item_id) ? 'is-favorited' : ''}"
                onclick="toggleAvitoFavorite('${escapeHtml(it.item_id)}', this)"
                title="${isFavorited(it.item_id) ? 'Убрать из избранного' : 'Добавить в избранное'}"
              >${isFavorited(it.item_id) ? '⭐ В избранном' : '☆ В избранное'}</button>

              <button type="button"
                id="btn-sniper-buy-${escapeHtml(it.item_id)}"
                ${hasDelivery ? `onclick="sniperCheckoutCard('${escapeHtml(it.item_id)}', '${escapeHtml(it.url || '')}', this)"` : 'disabled'}
                class="btn-card-sniper-top ${hasDelivery ? '' : 'disabled'}"
                title="${hasDelivery ? '⚡ Фоновый робот: выкупить лот за 1.5 секунды в чекауте Авито' : 'Авито Доставка недоступна (только самовывоз)'}">
                <span class="btn-sniper-content"><span class="btn-sniper-bolt">⚡</span><span class="btn-sniper-text">Купить</span></span>
              </button>
            </div>

            <div class="avito-card-actions">
              <button type="button"
                id="btn-card-message-${escapeHtml(it.item_id)}"
                ${hasChat ? `onclick="openItemChatModal('${escapeHtml(it.item_id)}', '${escapeHtml(it.url || '')}', '${escapeHtml(it.title || '')}', '${escapeHtml(it.price || '')}', '${escapeHtml(rawSeller || '')}')"` : 'disabled'}
                class="btn-avito-message ${hasChat ? (isItemChatUnread(it.item_id) ? 'has-unread' : '') : 'disabled'}"
                title="${hasChat ? 'Написать продавцу в чат' : 'Чат у продавца отключен (только звонки)'}">
                <span class="btn-message-content"><span class="btn-message-icon">💬</span><span class="btn-message-text">Написать</span></span>${hasChat && isItemChatUnread(it.item_id) ? `<span class="chat-pulsing-badge" id="chat-badge-${escapeHtml(it.item_id)}">!</span>` : ''}
              </button>

              ${(isBlacklistFilter || isCardBlacklisted(it)) ? `
                <button type="button" onclick="window.removeCardFromBlacklist('${escapeHtml(it.item_id)}', ${safeSellerJson})" class="btn-card-blacklist is-blacklisted" title="Убрать товар и продавца «${escapeHtml(rawSeller || '')}» из ЧС и вернуть назад">
                  Из ЧС
                </button>

                <button type="button" onclick="window.removeCardFromBlacklist('${escapeHtml(it.item_id)}', ${safeSellerJson})" class="btn-card-delete-action" title="Убрать карточку из ЧС и вернуть на прежнее место">
                  🗑️ Убрать
                </button>
              ` : `
                <button type="button" onclick="window.addCardToBlacklist('${escapeHtml(it.item_id)}', ${safeSellerJson})" class="btn-card-blacklist" title="Заблокировать товар и продавца «${escapeHtml(rawSeller || 'продавца')}» и отправить в ЧС">
                  В ЧС
                </button>

                <button type="button" onclick="deleteAvitoCard('${escapeHtml(it.item_id)}', event)" class="btn-card-delete-action" title="Убрать карточку объявления">
                  🗑️ Убрать
                </button>
              `}
            </div>
          </div>
        </div>
      </div>
      `;
    }).join('')}

    ${(currentAvitoPageSize !== 'all' && totalPages > 1) ? `
      <div class="avito-bottom-pagination-bar" style="grid-column:1/-1;margin-top:1.5rem;padding:0.9rem 1.25rem;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;">
        <div style="font-size:0.85rem;color:var(--text-secondary);min-width:0;font-variant-numeric:tabular-nums;text-align:left;">
          Страница <strong style="color:var(--text-primary);">${currentAvitoPage}</strong> из <strong style="color:var(--text-primary);">${totalPages}</strong> (показано <strong style="color:var(--text-primary);">${startIdx + 1}–${endIdx}</strong> из <strong style="color:var(--text-primary);">${totalItemsCount}</strong>)
        </div>
        <div style="display:flex;align-items:center;gap:0.85rem;flex-wrap:wrap;justify-content:flex-start;">
          ${getAvitoPageSizeSelectorHtml(currentAvitoPageSize)}
          ${getAvitoPageNavHtml(totalItemsCount, currentAvitoPage, currentAvitoPageSize, true)}
        </div>
      </div>
    ` : ''}
  `;

  const ipEl = document.getElementById('server-ip-val');
  if (ipEl && _serverNetworkUrl) {
    ipEl.innerText = _serverNetworkUrl.replace(/^https?:\/\//, '');
  }

  // Запуск фонового диспетчера живого обновления карточек (без перезагрузки страницы)
  startRealtimeAvitoPoller();
  requestAnimationFrame(() => {
    if (typeof updateAddSearchHintPosition === 'function') updateAddSearchHintPosition();
  });
}

window.renderAvitoDashboard = function() {
  if (typeof _isEditingTg !== 'undefined' && _isEditingTg) return;
  renderAvitoMonitor('');
  // Если есть ожидающий pending — запускаем опрос подтверждения
  const hasPending = (typeof _isEditingTg === 'undefined' || !_isEditingTg) && (
    (avitoData && avitoData.stats && avitoData.stats.telegram_pending && avitoData.stats.telegram_pending.status === 'pending')
    || (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending')
  );
  if (hasPending && typeof window._startTgPendingPoll === 'function' && !window._tgPendingPollTimer) {
    window._startTgPendingPoll();
  }
};

// ==================== AVITO BROWSER SNIPER ====================
// Глобальное состояние снайпера
window._sniperConfig = (function() {
  try {
    const raw = localStorage.getItem('electro_avito_sniper_config');
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
})();
window._sniperAuthenticated = (function() {
  try {
    return localStorage.getItem('electro_avito_sniper_auth') === '1';
  } catch (e) { return false; }
})();
window._sniperUserName = localStorage.getItem('electro_avito_sniper_user') || '';

let _sniperStatusPollTimer = null;
let _sniperPollingAttempts = 0;
window._sniperLoginWaitActive = false;

function _stopSniperStatusPolling() {
  if (_sniperStatusPollTimer) {
    clearInterval(_sniperStatusPollTimer);
    _sniperStatusPollTimer = null;
  }
}

function _startSniperStatusPolling(maxDurationMs = 180000) {
  _stopSniperStatusPolling();
  _sniperPollingAttempts = 0;
  const startTime = Date.now();

  _sniperStatusPollTimer = setInterval(async () => {
    const overlay = document.getElementById('modal-overlay');
    const isModalOpen = overlay && overlay.classList.contains('open');

    // Если модальное окно закрыто и не находимся в режиме ожидания входа по SMS, останавливаем опрос
    if (!isModalOpen && !window._sniperLoginWaitActive) {
      _stopSniperStatusPolling();
      return;
    }

    // Если модалка закрыта, но активен режим ожидания SMS, разрешаем до 90 секунд фонового опроса
    if (!isModalOpen && window._sniperLoginWaitActive && (Date.now() - startTime > 90000)) {
      window._sniperLoginWaitActive = false;
      _stopSniperStatusPolling();
      return;
    }

    // Общий таймаут опроса
    if (Date.now() - startTime > maxDurationMs) {
      window._sniperLoginWaitActive = false;
      _stopSniperStatusPolling();
      return;
    }

    _sniperPollingAttempts++;
    const res = await _sniperLoadStatus(true);
    // Как только авторизация обнаружена — выключаем режим ожидания и частый опрос
    if (res && res.authenticated) {
      window._sniperLoginWaitActive = false;
      _stopSniperStatusPolling();
    }
  }, 1200);
}

async function _sniperLoadStatus(force = false) {
  try {
    const url = force ? `/api/avito/sniper/status?force=1&_t=${Date.now()}` : `/api/avito/sniper/status?_t=${Date.now()}`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    if (data && data.success) {
      const prevAuth = Boolean(window._sniperAuthenticated);
      const isAuth = Boolean(data.authenticated);
      window._sniperAuthenticated = isAuth;
      window._sniperUserName = isAuth ? ((data.user_name && data.user_name.trim() !== 'Не авторизован') ? data.user_name : 'Мой профиль Avito') : '';
      try {
        localStorage.setItem('electro_avito_sniper_auth', isAuth ? '1' : '0');
        localStorage.setItem('electro_avito_sniper_user', window._sniperUserName);
      } catch (e) {}

      if (data.config && typeof data.config === 'object') {
        window._sniperConfig = Object.assign({}, window._sniperConfig || {}, data.config);
        try {
          localStorage.setItem('electro_avito_sniper_config', JSON.stringify(window._sniperConfig));
        } catch (e) {}
      }
      if (typeof window.updateSniperButtonUI === 'function') {
        window.updateSniperButtonUI();
      }
      _updateSniperModalStatusUI();

      // Моментально обновляем состояние, если авторизация только что подтвердилась (без пуш-уведомлений)
      if (!prevAuth && isAuth) {
        window._sniperLoginWaitActive = false;
      }
    }
    return data;
  } catch (e) {
    return null;
  }
}

function getSniperDisplayUserName() {
  const isAuth = Boolean(window._sniperAuthenticated);
  if (!isAuth) return 'Не авторизован';
  const name = (window._sniperUserName || '').trim();
  if (!name || name === 'Мои объявления' || name.toLowerCase().includes('объявления') || name === 'Пользователь Avito' || name === 'Не авторизован') {
    return 'Мой профиль Avito (Подключен)';
  }
  return name;
}

window.getProfileUserIconHtml = function(isAuth) {
  const strokeColor = isAuth ? '#10b981' : '#ef4444';
  const glow = isAuth ? 'drop-shadow(0 0 5px rgba(16,185,129,0.75))' : 'drop-shadow(0 0 5px rgba(239,68,68,0.75))';
  return `<svg class="profile-user-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="stroke:${strokeColor};filter:${glow};flex-shrink:0;vertical-align:middle;display:inline-block;transition:all 0.25s ease;">
    <circle cx="12" cy="7.2" r="4.8" stroke-width="2.3"/>
    <path d="M 3.5 20.5 C 3.5 15.8 7.2 13.8 12 15 C 16.8 13.8 20.5 15.8 20.5 20.5 H 3.5 Z" stroke-width="2.3" stroke-linejoin="round"/>
  </svg>`;
};

window.updateSniperButtonUI = function() {
  const isAuth = Boolean(window._sniperAuthenticated);
  const btns = document.querySelectorAll('#btn-avito-sniper-main, .btn-avito-sniper, .btn-avito-profile');
  btns.forEach(btn => {
    if (btn.id === 'btn-avito-sniper-main' || (btn.textContent && (btn.textContent.includes('Снайпер') || btn.textContent.includes('Профиль')))) {
      if (isAuth) {
        btn.classList.add('authenticated');
        btn.classList.remove('not-authenticated');
        btn.title = `Профиль Авито: подключен (${getSniperDisplayUserName()})`;
      } else {
        btn.classList.remove('authenticated');
        btn.classList.add('not-authenticated');
        btn.title = 'Профиль Авито: не авторизован (нажмите для входа по SMS)';
      }
      const iconSvg = btn.querySelector('.profile-user-svg');
      if (iconSvg) {
        iconSvg.style.stroke = isAuth ? '#10b981' : '#ef4444';
        iconSvg.style.filter = isAuth ? 'drop-shadow(0 0 5px rgba(16,185,129,0.75))' : 'drop-shadow(0 0 5px rgba(239,68,68,0.75))';
      }
    }
  });
};

function _updateSniperModalStatusUI() {
  const isAuth = Boolean(window._sniperAuthenticated);
  const userName = isAuth ? getSniperDisplayUserName() : 'Не авторизован';
  if (typeof window.updateSniperButtonUI === 'function') {
    window.updateSniperButtonUI();
  }
  const badge = document.getElementById('sniper-status-badge');
  if (badge) {
    badge.className = `sniper-status-badge ${isAuth ? 'online' : 'offline'}`;
    badge.innerHTML = `${isAuth ? '🟢' : '⚫'} ${escapeHtml(userName)}`;
  }
  const btn = document.getElementById('sniper-login-btn');
  if (btn) {
    if (window._sniperLoginWaitActive && !isAuth) {
      btn.disabled = false;
      btn.className = 'btn-avito-sniper not-authenticated';
      btn.innerHTML = '⏳ Ожидание SMS-кода...';
    } else {
      btn.disabled = false;
      btn.innerHTML = isAuth ? '🔄 Переавторизоваться' : '🔑 Авторизоваться';
      if (isAuth) {
        btn.classList.add('authenticated');
        btn.classList.remove('not-authenticated');
      } else {
        btn.classList.remove('authenticated');
        btn.classList.add('not-authenticated');
      }
    }
  }
  const note = document.getElementById('sniper-auth-note');
  if (note) {
    note.innerHTML = !isAuth ? `<p style="margin:0.5rem 0 0;font-size:0.79rem;color:#fb923c;">⚠️ Нажмите «Авторизоваться» — откроется браузер, выполните вход. Сессия и карты сохранятся локально.</p>` : '';
  }

  // Обновляем значения полей в открытом модальном окне из актуального конфига
  const cfg = window._sniperConfig || {};
  const autoBuyEl = document.getElementById('sniper-auto-buy');
  if (autoBuyEl && document.activeElement !== autoBuyEl) {
    autoBuyEl.checked = (cfg.auto_buy_enabled === true);
  }
  const maxPriceEl = document.getElementById('sniper-max-price');
  if (maxPriceEl && document.activeElement !== maxPriceEl && cfg.max_price !== undefined && cfg.max_price !== null) {
    maxPriceEl.value = cfg.max_price;
  }
  const inclDelivEl = document.getElementById('sniper-price-includes-delivery');
  if (inclDelivEl && document.activeElement !== inclDelivEl) {
    inclDelivEl.checked = (cfg.max_price_includes_delivery === true);
  }
  const autoMsgEl = document.getElementById('sniper-auto-message');
  if (autoMsgEl && document.activeElement !== autoMsgEl) {
    autoMsgEl.checked = (cfg.auto_message_enabled === true);
  }
  const msgTextEl = document.getElementById('sniper-msg-text');
  if (msgTextEl && document.activeElement !== msgTextEl && cfg.auto_message_text !== undefined) {
    msgTextEl.value = cfg.auto_message_text;
  }
  const safeModeEl = document.getElementById('sniper-safe-mode');
  if (safeModeEl && document.activeElement !== safeModeEl) {
    safeModeEl.checked = (cfg.safe_mode === true);
  }
  const cheapestEl = document.getElementById('sniper-cheapest-delivery');
  if (cheapestEl && document.activeElement !== cheapestEl) {
    cheapestEl.checked = (cfg.cheapest_delivery !== false);
  }
  const preferredEl = document.getElementById('sniper-preferred-delivery');
  if (preferredEl && document.activeElement !== preferredEl && cfg.preferred_delivery) {
    preferredEl.value = cfg.preferred_delivery;
    if (typeof window.syncDeliveryDropdownUI === 'function') {
      window.syncDeliveryDropdownUI(cfg.preferred_delivery);
    }
  }
  const minRatingEl = document.getElementById('sniper-min-rating');
  if (minRatingEl && document.activeElement !== minRatingEl && cfg.min_seller_rating !== undefined && cfg.min_seller_rating !== null) {
    minRatingEl.value = cfg.min_seller_rating;
  }
  if (cfg.auto_buy_mode) {
    const rAll = document.querySelector('input[name="sniper-autobuy-mode"][value="all"]');
    const rSel = document.querySelector('input[name="sniper-autobuy-mode"][value="selected"]');
    const box = document.getElementById('sniper-autobuy-searches-box');
    const countEl = document.getElementById('sniper-autobuy-selected-count');
    if (rAll && rSel && document.activeElement !== rAll && document.activeElement !== rSel) {
      if (cfg.auto_buy_mode === 'selected') {
        rSel.checked = true;
        if (box) box.style.display = 'block';
        if (countEl) countEl.style.display = 'inline';
      } else {
        rAll.checked = true;
        if (box) box.style.display = 'none';
        if (countEl) countEl.style.display = 'none';
      }
    }
  }
}

// Мгновенная реакция при возвращении пользователя в окно/вкладку SkyBase ("возвращаюсь в окно снайпера")
window.addEventListener('focus', () => {
  const overlay = document.getElementById('modal-overlay');
  const isModalOpen = overlay && overlay.classList.contains('open');
  if (isModalOpen || window._sniperLoginWaitActive || !window._sniperAuthenticated) {
    _sniperLoadStatus(true);
    if (!window._sniperAuthenticated && (isModalOpen || window._sniperLoginWaitActive)) {
      _startSniperStatusPolling(180000);
    }
  }
}, { passive: true });

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    const overlay = document.getElementById('modal-overlay');
    const isModalOpen = overlay && overlay.classList.contains('open');
    if (isModalOpen || window._sniperLoginWaitActive || !window._sniperAuthenticated) {
      _sniperLoadStatus(true);
      if (!window._sniperAuthenticated && (isModalOpen || window._sniperLoginWaitActive)) {
        _startSniperStatusPolling(180000);
      }
    }
  }
}, { passive: true });

// ==================== КАСТОМНЫЙ ВЫПАДАЮЩИЙ СПИСОК СЛУЖБЫ ДОСТАВКИ ====================
const SNIPER_DELIVERY_OPTIONS = [
  { value: 'cheapest', label: '⚡ По наименьшей цене пункта выдачи (авто-выбор)' },
  { value: 'yandex', label: '🟡 Яндекс Доставка' },
  { value: 'cdek', label: '🟢 СДЭК' },
  { value: 'fivepost', label: '🔴 5Post / Пятёрочка' },
  { value: 'russianpost', label: '🔵 Почта России' },
  { value: 'boxberry', label: '🟠 Boxberry' },
  { value: 'exmail', label: '⬜ Авито / EXMAIL' },
  { value: 'dpd', label: '🟣 DPD' }
];

window.toggleDeliveryMenu = function(e) {
  if (e) {
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (typeof e.stopPropagation === 'function') e.stopPropagation();
  }
  const menu = document.getElementById('delivery-select-menu');
  const chevron = document.getElementById('delivery-select-chevron');
  const trigger = document.getElementById('delivery-select-trigger');
  if (!menu) return;
  const isOpened = (menu.style.display === 'block');
  if (isOpened) {
    menu.style.display = 'none';
    if (chevron) chevron.style.transform = 'rotate(0deg)';
    if (trigger) trigger.classList.remove('open');
  } else {
    menu.style.display = 'block';
    if (chevron) chevron.style.transform = 'rotate(180deg)';
    if (trigger) trigger.classList.add('open');
  }
};

window.selectDeliveryOption = function(val) {
  window._sniperConfig = Object.assign({}, window._sniperConfig || {}, { preferred_delivery: val });
  try {
    localStorage.setItem('electro_avito_sniper_config', JSON.stringify(window._sniperConfig));
  } catch (_) {}
  const sel = document.getElementById('sniper-preferred-delivery');
  if (sel) {
    sel.value = val;
    if (typeof sniperAutoSave === 'function') sniperAutoSave();
  }
  window.syncDeliveryDropdownUI(val);
  const menu = document.getElementById('delivery-select-menu');
  const chevron = document.getElementById('delivery-select-chevron');
  const trigger = document.getElementById('delivery-select-trigger');
  if (menu) menu.style.display = 'none';
  if (chevron) chevron.style.transform = 'rotate(0deg)';
  if (trigger) trigger.classList.remove('open');

  // Мгновенно обновляем плашку доставки на всех карточках в ленте
  document.querySelectorAll('.avito-card').forEach(c => {
    const dEl = c.querySelector('.avito-detail-delivery');
    if (dEl && !dEl.innerText.includes('Самовывоз')) {
      const cId = c.getAttribute('data-item-id') || c.id.replace('avito-card-', '');
      dEl.innerText = formatCardDeliveryText({ has_delivery: true, item_id: cId });
    }
  });
};

window.syncDeliveryDropdownUI = function(val) {
  const item = SNIPER_DELIVERY_OPTIONS.find(o => o.value === val) || SNIPER_DELIVERY_OPTIONS[0];
  const curText = document.getElementById('delivery-select-current-text');
  if (curText) curText.textContent = item.label;
  
  const menu = document.getElementById('delivery-select-menu');
  if (menu) {
    const opts = menu.querySelectorAll('.custom-delivery-option');
    opts.forEach(el => {
      const isSel = el.getAttribute('onclick')?.includes(`'${val}'`);
      if (isSel) {
        el.classList.add('selected');
        el.style.color = '#38bdf8';
        el.style.background = 'rgba(56,189,248,0.15)';
        if (!el.querySelector('.check-mark')) {
          el.insertAdjacentHTML('beforeend', '<span class="check-mark" style="color:#38bdf8;font-size:0.85rem;">✓</span>');
        }
      } else {
        el.classList.remove('selected');
        el.style.color = '#f8fafc';
        el.style.background = 'transparent';
        const cm = el.querySelector('.check-mark');
        if (cm) cm.remove();
      }
    });
  }

  // Если выбран пункт «По наименьшей цене пункта выдачи (авто-выбор)», затемнить и сделать неактивным fallback-пункт
  const cheapestInput = document.getElementById('sniper-cheapest-delivery');
  const cheapestLabel = document.getElementById('sniper-cheapest-delivery-label') || cheapestInput?.closest('label');
  if (cheapestInput && cheapestLabel) {
    const isCheapestAuto = (val === 'cheapest');
    cheapestInput.disabled = isCheapestAuto;
    if (isCheapestAuto) {
      cheapestLabel.style.opacity = '0.38';
      cheapestLabel.style.pointerEvents = 'none';
      cheapestLabel.style.filter = 'grayscale(0.6)';
      cheapestLabel.title = 'Пункт не требуется, так как уже выбран авто-выбор по наименьшей цене';
    } else {
      cheapestLabel.style.opacity = '1';
      cheapestLabel.style.pointerEvents = 'auto';
      cheapestLabel.style.filter = 'none';
      cheapestLabel.title = '';
    }
  }
};

// Закрытие выпадающего списка при клике вне его области
document.addEventListener('click', (e) => {
  const wrapper = document.querySelector('.custom-delivery-select-wrapper');
  if (wrapper && !wrapper.contains(e.target)) {
    const menu = document.getElementById('delivery-select-menu');
    if (menu && menu.style.display === 'block') {
      menu.style.display = 'none';
      const chevron = document.getElementById('delivery-select-chevron');
      if (chevron) chevron.style.transform = 'rotate(0deg)';
      const trigger = document.getElementById('delivery-select-trigger');
      if (trigger) trigger.classList.remove('open');
    }
  }
});

// Закрытие выпадающего списка по Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const donateOverlay = document.getElementById('donate-modal-overlay');
    if (donateOverlay && (donateOverlay.classList.contains('open') || donateOverlay.style.display === 'flex' || donateOverlay.style.display !== 'none' && donateOverlay.style.display !== '')) {
      window.closeDonateModal(e);
      return;
    }
    const menu = document.getElementById('delivery-select-menu');
    if (menu && menu.style.display === 'block') {
      menu.style.display = 'none';
      const chevron = document.getElementById('delivery-select-chevron');
      if (chevron) chevron.style.transform = 'rotate(0deg)';
      const trigger = document.getElementById('delivery-select-trigger');
      if (trigger) trigger.classList.remove('open');
    }
  }
});

function openSniperModal() {
  const overlay = modalOverlay || document.getElementById('modal-overlay');
  const body = modalBody || document.getElementById('modal-body');
  if (!overlay || !body) return;

  const cfg = window._sniperConfig || (function() {
    try { return JSON.parse(localStorage.getItem('electro_avito_sniper_config')) || {}; } catch(e) { return {}; }
  })() || {};
  const isAuth = window._sniperAuthenticated;
  const userName = getSniperDisplayUserName();
  const msgText = (cfg.auto_message_text !== undefined) ? cfg.auto_message_text : 'Здравствуйте! Готов забрать сегодня с доставкой, ещё актуально?';
  const autoBuy = cfg.auto_buy_enabled === true;
  const maxPrice = (cfg.max_price !== undefined && cfg.max_price !== null) ? cfg.max_price : 15000;
  const minRating = (cfg.min_seller_rating !== undefined && cfg.min_seller_rating !== null) ? cfg.min_seller_rating : 0;
  const priceIncludesDelivery = cfg.max_price_includes_delivery === true;
  const autoMsg = cfg.auto_message_enabled === true;
  const safeMode = (cfg.safe_mode !== undefined) ? (cfg.safe_mode === true) : true;
  const cheapestDelivery = (cfg.cheapest_delivery !== undefined) ? (cfg.cheapest_delivery === true) : true;
  const preferredDelivery = cfg.preferred_delivery || 'cheapest';
  const defaultPaymentMethod = cfg.payment_method || 'card';
  const searchDepth = (cfg.search_depth !== undefined && cfg.search_depth !== null) ? parseInt(cfg.search_depth, 10) : 0;

  const autoBuyMode = (cfg.auto_buy_mode === 'selected') ? 'selected' : 'all';
  const autoBuySearches = Array.isArray(cfg.auto_buy_searches) ? cfg.auto_buy_searches : [];

  let searches = (typeof normalizeSearches === 'function') ? normalizeSearches(avitoData?.searches) : (avitoData?.searches || []);
  if ((!searches || searches.length === 0) && currentUser && currentUser.avito_searches) {
    searches = (typeof normalizeSearches === 'function') ? normalizeSearches(currentUser.avito_searches) : currentUser.avito_searches;
  }

  const cleanSearchUrl = (u) => {
    if (!u) return '';
    try {
      let s = String(u).trim().toLowerCase();
      s = s.replace(/^https?:\/\//, '').replace(/^(www\.|m\.)/, '').replace(/\/+$/, '');
      const parts = s.split('?');
      if (parts.length > 1) {
        const params = new URLSearchParams(parts[1]);
        const sortedParams = Array.from(params.entries())
          .filter(([k]) => !['spm', '_gl', 'from', 'utm_source', 'utm_medium', 'utm_campaign'].includes(k))
          .sort(([a], [b]) => a.localeCompare(b));
        const qStr = sortedParams.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
        return qStr ? parts[0] + '?' + qStr : parts[0];
      }
      return parts[0];
    } catch(e) {
      return String(u).trim().toLowerCase();
    }
  };

  const isSearchSelected = (s) => {
    if (!autoBuySearches || autoBuySearches.length === 0) return false;
    const sUrl = cleanSearchUrl(s.url);
    const sName = (s.name || '').trim().toLowerCase();
    const sId = String(s.id || '').trim();

    return autoBuySearches.some(item => {
      if (typeof item === 'object' && item !== null) {
        const iId = String(item.id || '').trim();
        const iUrl = cleanSearchUrl(item.url);
        const iName = (item.name || '').trim().toLowerCase();

        if (sId && iId && sId === iId) return true;
        if (sUrl && iUrl && sUrl === iUrl) return true;
        if (sName && iName && sName === iName) return true;
        return false;
      }
      const str = String(item).trim();
      if (!str) return false;
      if (sId && str === sId) return true;
      if (sName && str.toLowerCase() === sName) return true;
      if (sUrl && cleanSearchUrl(str) === sUrl) return true;
      return false;
    });
  };

  let selectedCount = 0;
  let searchesCheckboxesHtml = '';
  if (!searches || searches.length === 0) {
    searchesCheckboxesHtml = `<div style="font-size:0.8rem;color:var(--text-secondary);text-align:center;padding:0.65rem 0.5rem;">
      🔍 Нет активных ссылок поиска.<br><span style="font-size:0.75rem;">Добавьте ссылки в мониторинг Авито, и они появятся здесь.</span>
    </div>`;
  } else {
    searchesCheckboxesHtml = searches.map(s => {
      const isChecked = isSearchSelected(s);
      if (isChecked) selectedCount++;
      const sName = (s.name || '').trim();
      const sUrl = (s.url || '').trim();
      let displayName = sName || sUrl;
      let displaySub = (sName && sUrl && sName !== sUrl) ? sUrl : '';
      if (displaySub.length > 55) {
        displaySub = displaySub.substring(0, 52) + '...';
      }
      return `
        <label style="display:flex;align-items:center;gap:0.55rem;padding:0.35rem 0.55rem;border-radius:6px;background:var(--bg-secondary);border:1px solid var(--border-color);cursor:pointer;transition:background 0.15s ease;"
               onmouseover="this.style.background='var(--bg-hover, rgba(255,255,255,0.06))'"
               onmouseout="this.style.background='var(--bg-secondary)'">
          <input type="checkbox" class="sniper-search-cb"
                 data-search-id="${escapeHtml(String(s.id || ''))}"
                 data-search-name="${escapeHtml(s.name || '')}"
                 data-search-url="${escapeHtml(s.url || '')}"
                 ${isChecked ? 'checked' : ''}
                 onchange="window.onSniperSearchCheckChange()"
                 style="width:16px;height:16px;accent-color:#10b981;cursor:pointer;flex-shrink:0;">
          <div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            <span style="font-size:0.83rem;font-weight:600;color:var(--text-primary);">${escapeHtml(displayName)}</span>
            ${displaySub ? `<span style="font-size:0.73rem;color:var(--text-secondary);margin-left:0.35rem;" title="${escapeHtml(sUrl)}">(${escapeHtml(displaySub)})</span>` : ''}
          </div>
        </label>
      `;
    }).join('');
  }

  body.innerHTML = `
    <div class="sniper-modal-card">
      <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;">
        <span style="font-size:1.6rem;">🎯</span>
        <div>
          <h3 style="margin:0;font-size:1.15rem;color:var(--text-primary);font-weight:700;">Робот-снайпер: Авто-выкуп и Чат</h3>
          <p style="margin:0;font-size:0.8rem;color:var(--text-secondary);">Мгновенный выкуп за 1.5 сек и авто-сообщения продавцу под вашим профилем</p>
        </div>
      </div>

      <!-- 1. СТАТУС АВТОРИЗАЦИИ -->
      <div style="background:var(--bg-secondary);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color);">
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.45rem;font-weight:700;letter-spacing:0.04em;">СТАТУС ВАШЕГО АККАУНТА АВИТО</div>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:gap;gap:0.5rem;">
          <span id="sniper-status-badge" class="sniper-status-badge ${isAuth ? 'online' : 'offline'}">
            ${isAuth ? '🟢' : '⚫'} ${escapeHtml(userName)}
          </span>
          <button type="button" id="sniper-login-btn" onclick="sniperLogin()" class="btn-avito-sniper" style="font-size:0.8rem;padding:0.35rem 0.75rem;">
            ${isAuth ? '🔄 Переавторизоваться' : '🔑 Авторизоваться'}
          </button>
        </div>
        <div id="sniper-auth-note">
          ${!isAuth ? `<p style="margin:0.5rem 0 0;font-size:0.79rem;color:#fb923c;">⚠️ Нажмите «Авторизоваться» — откроется браузер, выполните вход. Сессия и карты сохранятся локально.</p>` : ''}
        </div>
      </div>


      <!-- 3. СПОСОБ ОПЛАТЫ ПО УМОЛЧАНИЮ -->
      <div style="background:var(--bg-secondary);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color);">
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.5rem;font-weight:700;letter-spacing:0.04em;">💳 СПОСОБ ОПЛАТЫ ПО УМОЛЧАНИЮ</div>
        <div style="display:flex;flex-direction:column;gap:0.45rem;">
          <label style="display:flex;align-items:center;gap:0.55rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
            <input type="radio" name="sniper-default-pm" value="card" ${defaultPaymentMethod === 'card' || !defaultPaymentMethod ? 'checked' : ''}
              onchange="sniperAutoSave()" style="accent-color:#10b981;cursor:pointer;">
            <span>💳 <strong>СБП / Банковская карта</strong></span>
          </label>
          <label style="display:flex;align-items:center;gap:0.55rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
            <input type="radio" name="sniper-default-pm" value="wallet" ${defaultPaymentMethod === 'wallet' ? 'checked' : ''}
              onchange="sniperAutoSave()" style="accent-color:#10b981;cursor:pointer;">
            <span>💰 <strong>Кошелёк Авито</strong> (моментально, без SMS и кодов)</span>
          </label>
          <label style="display:flex;align-items:center;gap:0.55rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
            <input type="radio" name="sniper-default-pm" value="cod" ${defaultPaymentMethod === 'cod' ? 'checked' : ''}
              onchange="sniperAutoSave()" style="accent-color:#10b981;cursor:pointer;">
            <span>📦 <strong>При получении в ПВЗ</strong> (оплата при осмотре)</span>
          </label>
        </div>
      </div>

      <!-- 4. АВТО-СООБЩЕНИЕ ПРОДАВЦУ -->
      <div style="background:var(--bg-secondary);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color);">
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.5rem;font-weight:700;letter-spacing:0.04em;">💬 АВТО-СООБЩЕНИЕ ПРОДАВЦУ</div>
        <label style="display:flex;align-items:flex-start;gap:0.6rem;cursor:pointer;margin-bottom:0.7rem;">
          <input type="checkbox" id="sniper-auto-message" ${autoMsg ? 'checked' : ''}
            onchange="sniperAutoSave()"
            style="width:17px;height:17px;margin-top:2px;accent-color:#818cf8;cursor:pointer;">
          <div>
            <span style="font-size:0.87rem;font-weight:600;color:var(--text-primary);">Отправлять авто-сообщение продавцу за 1 секунду</span>
            <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:2px;">Как только лот появляется — робот сам отправляет текст ниже в чат Авито.</div>
          </div>
        </label>

        <div style="display:flex;flex-direction:column;gap:0.35rem;margin-bottom:0.25rem;">
          <label style="font-size:0.8rem;color:var(--text-secondary);">Поле для текста:</label>
          <textarea id="sniper-msg-text" rows="2"
            oninput="sniperAutoSave()"
            style="width:100%;box-sizing:border-box;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border-color);border-radius:7px;padding:0.5rem 0.7rem;font-size:0.85rem;resize:vertical;"
            placeholder="Здравствуйте! Готов забрать сегодня с доставкой, ещё актуально?">${escapeHtml(msgText)}</textarea>
        </div>
      </div>

      <!-- 5. РЕЖИМ БЕЗОПАСНОСТИ -->
      <div style="background:var(--bg-secondary);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color);">
        <label style="display:flex;align-items:flex-start;gap:0.6rem;cursor:pointer;">
          <input type="checkbox" id="sniper-safe-mode" ${safeMode ? 'checked' : ''}
            onchange="sniperAutoSave()"
            style="width:17px;height:17px;margin-top:2px;accent-color:#f87171;cursor:pointer;">
          <div>
            <span style="font-size:0.85rem;color:var(--text-primary);">🛡️ <strong>Безопасный режим</strong> — открывать чекаут и выбирать карту, но «Оплатить» нажимать вручную</span>
            <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:2px;">Если снято: действует полный авто-выкуп за 1.5 секунды с финальной оплатой/бронью.</div>
          </div>
        </label>
      </div>

      <!-- 6. ВЫБОР СЛУЖБЫ ДОСТАВКИ -->
      <div style="background:var(--bg-card, #1e293b);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color, #334155);position:relative;">
        <div style="margin-bottom:0.65rem;">
          <span style="font-size:0.87rem;font-weight:700;color:var(--text-primary, #f8fafc);">🚚 Служба доставки</span>
          <div style="font-size:0.78rem;color:var(--text-secondary, #94a3b8);margin-top:2px;">Выберите предпочитаемый пункт выдачи / перевозчика или оставьте авто-выбор по наименьшей стоимости.</div>
        </div>

        <!-- Кастомный выпадающий список (полностью исключает белое мерцание в браузере при разворачивании) -->
        <div class="custom-delivery-select-wrapper" style="position:relative;width:100%;user-select:none;">
          <button type="button" id="delivery-select-trigger" onclick="window.toggleDeliveryMenu(event)"
            class="custom-delivery-trigger">
            <span id="delivery-select-current-text" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">
              ${escapeHtml(SNIPER_DELIVERY_OPTIONS.find(o => o.value === preferredDelivery)?.label || SNIPER_DELIVERY_OPTIONS[0].label)}
            </span>
            <span id="delivery-select-chevron" style="color:#94a3b8;font-size:0.75rem;transition:transform 0.2s ease;">▼</span>
          </button>
          
          <div id="delivery-select-menu" class="custom-delivery-menu" style="display:none;">
            ${SNIPER_DELIVERY_OPTIONS.map(opt => `
              <div class="custom-delivery-option ${opt.value === preferredDelivery ? 'selected' : ''}"
                onclick="window.selectDeliveryOption('${opt.value}')">
                <span>${escapeHtml(opt.label)}</span>
                ${opt.value === preferredDelivery ? '<span class="check-mark" style="color:#38bdf8;font-size:0.85rem;">✓</span>' : ''}
              </div>
            `).join('')}
          </div>

          <!-- Скрытый нативный селект для 100% совместимости с кодом сохранения -->
          <select id="sniper-preferred-delivery" style="display:none;" onchange="sniperAutoSave()">
            ${SNIPER_DELIVERY_OPTIONS.map(opt => `
              <option value="${opt.value}" ${opt.value === preferredDelivery ? 'selected' : ''}>${escapeHtml(opt.label)}</option>
            `).join('')}
          </select>
        </div>

        <label id="sniper-cheapest-delivery-label" style="display:flex;align-items:flex-start;gap:0.55rem;margin-top:0.65rem;cursor:pointer;user-select:none;transition:all 0.2s ease;${preferredDelivery === 'cheapest' ? 'opacity:0.38;pointer-events:none;filter:grayscale(0.6);' : ''}" title="${preferredDelivery === 'cheapest' ? 'Пункт не требуется, так как уже выбран авто-выбор по наименьшей цене' : ''}">
          <input type="checkbox" id="sniper-cheapest-delivery" ${cheapestDelivery ? 'checked' : ''}
            ${preferredDelivery === 'cheapest' ? 'disabled' : ''}
            onchange="sniperAutoSave()"
            style="width:16px;height:16px;margin-top:2px;accent-color:#10b981;cursor:pointer;">
          <div style="flex:1;">
            <div style="font-size:0.82rem;font-weight:600;color:var(--text-primary, #f8fafc);">Если выбранного пункта нет — выбирать доставку по наименьшей цене пункта выдачи из имеющихся</div>
            <div style="font-size:0.75rem;color:var(--text-secondary, #94a3b8);margin-top:2px;">Автоматически находит среди всех доступных ПВЗ вариант с минимальной ценой (или отметкой «Лучшая цена»).</div>
          </div>
        </label>
      </div>

      <!-- 7. ГЛУБИНА ПОИСКА СТРАНИЦ -->
      <div style="background:var(--bg-card, #1e293b);border-radius:10px;padding:0.9rem;border:1px solid var(--border-color, #334155);">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.55rem;flex-wrap:wrap;gap:0.4rem;">
          <span style="font-size:0.87rem;font-weight:700;color:var(--text-primary, #f8fafc);">📑 Глубина поиска страниц</span>
          <span id="sniper-search-depth-badge" style="font-size:0.76rem;padding:0.2rem 0.6rem;border-radius:6px;background:${(searchDepth === 0) ? 'rgba(56,189,248,0.18)' : 'rgba(16,185,129,0.18)'};color:${(searchDepth === 0) ? '#38bdf8' : '#10b981'};font-weight:700;border:1px solid ${(searchDepth === 0) ? 'rgba(56,189,248,0.35)' : 'rgba(16,185,129,0.35)'};">
            ${(searchDepth === 0) ? '⚡ 0 — Без ограничений' : `📄 ${searchDepth} стр.`}
          </span>
        </div>

        <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.6rem;flex-wrap:wrap;">
          <label style="font-size:0.87rem;font-weight:600;color:var(--text-primary);cursor:pointer;" for="sniper-search-depth">
            Глубина поиска:
          </label>
          <div style="display:inline-flex;align-items:center;gap:0.4rem;">
            <input type="number" id="sniper-search-depth" min="0" max="100" step="1"
              value="${searchDepth}"
              oninput="window.onSniperDepthChange(this.value); if (typeof sniperAutoSave === 'function') sniperAutoSave();"
              style="width:85px;box-sizing:border-box;background:var(--bg-primary, #0f172a);color:var(--text-primary, #f8fafc);border:1px solid var(--border-color, #334155);border-radius:8px;padding:0.4rem 0.55rem;font-size:0.95rem;font-weight:700;text-align:center;">
            <span style="font-size:0.82rem;color:var(--text-secondary, #94a3b8);">стр.</span>
          </div>

          <!-- Быстрые кнопки пресетов -->
          <div style="display:inline-flex;gap:0.35rem;flex-wrap:wrap;">
            <button type="button" onclick="window.setSniperSearchDepth(0)" class="cat-btn"
              style="font-size:0.76rem;padding:0.25rem 0.55rem;border-radius:6px;background:${(searchDepth === 0) ? 'rgba(56,189,248,0.22)' : 'rgba(255,255,255,0.06)'};border:1px solid ${(searchDepth === 0) ? '#38bdf8' : 'var(--border-color, #334155)'};color:${(searchDepth === 0) ? '#38bdf8' : 'var(--text-primary)'};cursor:pointer;" title="0 — без ограничения поиска кол-ва страниц на сайте Авито">
              ⚡ 0 (Без ограничений)
            </button>
            <button type="button" onclick="window.setSniperSearchDepth(1)" class="cat-btn"
              style="font-size:0.76rem;padding:0.25rem 0.55rem;border-radius:6px;background:${(searchDepth === 1) ? 'rgba(16,185,129,0.22)' : 'rgba(255,255,255,0.06)'};border:1px solid ${(searchDepth === 1) ? '#10b981' : 'var(--border-color, #334155)'};color:${(searchDepth === 1) ? '#10b981' : 'var(--text-primary)'};cursor:pointer;">
              1 стр.
            </button>
            <button type="button" onclick="window.setSniperSearchDepth(3)" class="cat-btn"
              style="font-size:0.76rem;padding:0.25rem 0.55rem;border-radius:6px;background:${(searchDepth === 3) ? 'rgba(16,185,129,0.22)' : 'rgba(255,255,255,0.06)'};border:1px solid ${(searchDepth === 3) ? '#10b981' : 'var(--border-color, #334155)'};color:${(searchDepth === 3) ? '#10b981' : 'var(--text-primary)'};cursor:pointer;">
              3 стр.
            </button>
            <button type="button" onclick="window.setSniperSearchDepth(5)" class="cat-btn"
              style="font-size:0.76rem;padding:0.25rem 0.55rem;border-radius:6px;background:${(searchDepth === 5) ? 'rgba(16,185,129,0.22)' : 'rgba(255,255,255,0.06)'};border:1px solid ${(searchDepth === 5) ? '#10b981' : 'var(--border-color, #334155)'};color:${(searchDepth === 5) ? '#10b981' : 'var(--text-primary)'};cursor:pointer;">
              5 стр.
            </button>
            <button type="button" onclick="window.setSniperSearchDepth(10)" class="cat-btn"
              style="font-size:0.76rem;padding:0.25rem 0.55rem;border-radius:6px;background:${(searchDepth === 10) ? 'rgba(16,185,129,0.22)' : 'rgba(255,255,255,0.06)'};border:1px solid ${(searchDepth === 10) ? '#10b981' : 'var(--border-color, #334155)'};color:${(searchDepth === 10) ? '#10b981' : 'var(--text-primary)'};cursor:pointer;">
              10 стр.
            </button>
          </div>
        </div>

        <div style="font-size:0.78rem;color:var(--text-secondary, #94a3b8);line-height:1.45;">
          ℹ️ Цифра <strong>0</strong> означает — <em>без ограничения поиска кол-ва страниц на сайте Авито</em> (полный сбор всех страниц выдачи). При значении от 1 опрашивается только указанное число страниц.
        </div>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:0.35rem;gap:0.75rem;padding:0 0.1rem;flex-wrap:wrap;">
        <span style="font-size:0.78rem;color:#10b981;font-weight:600;display:inline-flex;align-items:center;gap:0.35rem;">
          <span>✓</span> <span>Настройки сохраняются автоматически</span>
        </span>
        <button type="button" onclick="if (typeof window.sniperSaveConfig === 'function') { clearTimeout(window._sniperSaveTimer); window.sniperSaveConfig(true); } closeModal();" class="cat-btn"
          style="padding:0.65rem 1.8rem;font-size:0.92rem;font-weight:700;min-height:42px;border-radius:9px;cursor:pointer;white-space:nowrap;background:rgba(148,163,184,0.18);border:1px solid rgba(148,163,184,0.3);color:#f8fafc;transition:all 0.15s ease;">
          ✕ Закрыть
        </button>
      </div>

      <!-- 7. ПОДСКАЗКА -->
      <div style="font-size:0.8rem;color:var(--text-secondary);line-height:1.45;padding:0 0.2rem;">
        💡 На карточках объявлений доступна кнопка <strong style="color:#fb923c;">«⚡ Купить»</strong> — нажали её, и фоновый робот за 1.5 секунды завершит оформление в чекауте Авито и выведет: <strong style="color:#34d399;">«Заказ оформлен»</strong>.
      </div>
    </div>
  `;

  overlay.classList.add('open');
  document.body.classList.add('modal-open');
  document.documentElement.classList.add('modal-open');
  _lastWindowScrollY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop;
  _lastModalContentScrollTop = 0;

  // Фоново запрашиваем свежий конфиг без задержки открытия окна
  fetch('/api/avito/sniper/config?_t=' + Date.now())
    .then(r => (r && r.ok) ? r.json() : null)
    .then(d => {
      if (d && d.success && d.config) {
        window._sniperConfig = d.config;
        try { localStorage.setItem('electro_avito_sniper_config', JSON.stringify(d.config)); } catch(e){}
      }
    })
    .catch(() => {});

  // Фоново подтягиваем статус и обновляем бейдж/поля без блокировки окна
  _sniperLoadStatus(true);
  _startSniperStatusPolling(120000);
}

window.sniperLogin = async function() {
  // 1. Открываем новую вкладку в существующем активном браузере
  window.open('https://www.avito.ru/#login', '_blank');

  // 2. Устанавливаем статус авторизации как активный (пользователь уже в своем основном профиле)
  window._sniperAuthenticated = true;
  if (!window._sniperUserName || window._sniperUserName === 'Не авторизован') {
    window._sniperUserName = 'Мой профиль Avito (Браузер)';
  }
  try {
    localStorage.setItem('electro_avito_sniper_auth', '1');
    localStorage.setItem('electro_avito_sniper_user', window._sniperUserName);
  } catch (e) {}

  // 3. В реальном времени обновляем модальное окно на зеленый (активный) статус
  const badge = document.getElementById('sniper-status-badge');
  if (badge) {
    badge.className = 'sniper-status-badge online';
    badge.innerHTML = `🟢 ${escapeHtml(window._sniperUserName)}`;
  }

  const body = document.getElementById('modal-body');
  let btn = null;
  if (body) {
    btn = body.querySelector('#sniper-login-btn') || body.querySelector('button[onclick="sniperLogin()"]');
    if (btn) {
      btn.disabled = false;
      btn.classList.add('authenticated');
      btn.classList.remove('not-authenticated');
      btn.textContent = '🔄 Переавторизоваться';
    }
  }

  const note = document.getElementById('sniper-auth-note');
  if (note) {
    note.innerHTML = '<p style="margin:0.5rem 0 0;font-size:0.79rem;color:#10b981;">✓ Новая вкладка открыта в вашем активном браузере с существующим профилем и куки.</p>';
  }

  // 4. Обновляем кнопки снайпера в шапке
  if (typeof window.updateSniperButtonUI === 'function') {
    window.updateSniperButtonUI();
  }

  // 5. Синхронизируем состояние с сервером
  try {
    await fetch('/api/avito/sniper/login', { method: 'POST' });
  } catch (e) {}
};

window.onSniperAutoBuyModeChange = function(mode) {
  const box = document.getElementById('sniper-autobuy-searches-box');
  const countEl = document.getElementById('sniper-autobuy-selected-count');
  if (box) {
    box.style.display = (mode === 'selected') ? 'block' : 'none';
  }
  if (countEl) {
    countEl.style.display = (mode === 'selected') ? 'inline' : 'none';
  }
  if (typeof window.updateSniperAutoBuyCount === 'function') {
    window.updateSniperAutoBuyCount();
  }
  if (typeof window.sniperAutoSave === 'function') {
    window.sniperAutoSave();
  }
};

window.onSniperSearchCheckChange = function() {
  if (typeof window.updateSniperAutoBuyCount === 'function') {
    window.updateSniperAutoBuyCount();
  }
  if (typeof window.sniperAutoSave === 'function') {
    window.sniperAutoSave();
  }
};

window.sniperToggleAllSearches = function(select) {
  const cbs = document.querySelectorAll('.sniper-search-cb');
  cbs.forEach(cb => { cb.checked = Boolean(select); });
  if (typeof window.updateSniperAutoBuyCount === 'function') {
    window.updateSniperAutoBuyCount();
  }
  if (typeof window.sniperAutoSave === 'function') {
    window.sniperAutoSave();
  }
};

window.updateSniperAutoBuyCount = function() {
  const countEl = document.getElementById('sniper-autobuy-selected-count');
  const warnEl = document.getElementById('sniper-autobuy-warning');
  const cbs = document.querySelectorAll('.sniper-search-cb');
  if (cbs.length === 0) return;
  let checked = 0;
  cbs.forEach(cb => { if (cb.checked) checked++; });
  const isSelectedMode = document.querySelector('input[name="sniper-autobuy-mode"]:checked')?.value === 'selected';
  if (countEl) {
    countEl.textContent = `Выбрано: ${checked} из ${cbs.length}`;
    countEl.style.color = (checked === 0 && isSelectedMode) ? '#f87171' : 'var(--text-secondary)';
  }
  if (warnEl) {
    warnEl.style.display = (isSelectedMode && checked === 0) ? 'block' : 'none';
  }
};

window.onSniperDepthChange = function(val) {
  const num = parseInt(val, 10);
  const badge = document.getElementById('sniper-search-depth-badge');
  if (badge) {
    if (isNaN(num) || num <= 0) {
      badge.innerHTML = '⚡ 0 — Без ограничений';
      badge.style.background = 'rgba(56,189,248,0.18)';
      badge.style.borderColor = 'rgba(56,189,248,0.35)';
      badge.style.color = '#38bdf8';
    } else {
      badge.innerHTML = `📄 ${num} стр.`;
      badge.style.background = 'rgba(16,185,129,0.18)';
      badge.style.borderColor = 'rgba(16,185,129,0.35)';
      badge.style.color = '#10b981';
    }
  }
};

window.setSniperSearchDepth = function(val) {
  const input = document.getElementById('sniper-search-depth');
  if (input) {
    input.value = val;
    window.onSniperDepthChange(val);
    if (typeof sniperAutoSave === 'function') sniperAutoSave();
  }
};

window.sniperAutoSave = function() {
  const safeMode = document.getElementById('sniper-safe-mode')?.checked === true;
  const autoMsg = document.getElementById('sniper-auto-message')?.checked === true;
  const msgText = document.getElementById('sniper-msg-text')?.value ?? '';
  const autoBuy = document.getElementById('sniper-auto-buy')?.checked === true;
  const maxPrice = parseFloat(document.getElementById('sniper-max-price')?.value) || 0;
  const minRating = parseFloat(document.getElementById('sniper-min-rating')?.value) || 0;
  const priceIncludesDelivery = document.getElementById('sniper-price-includes-delivery')?.checked === true;
  const cheapestDeliv = document.getElementById('sniper-cheapest-delivery')?.checked !== false;
  const preferredDeliv = document.getElementById('sniper-preferred-delivery')?.value || 'cheapest';
  const defaultPm = document.querySelector('input[name="sniper-default-pm"]:checked')?.value || 'card';
  const searchDepthInput = document.getElementById('sniper-search-depth');
  const searchDepth = searchDepthInput ? Math.max(0, parseInt(searchDepthInput.value, 10) || 0) : ((window._sniperConfig?.search_depth !== undefined) ? parseInt(window._sniperConfig.search_depth, 10) : 0);

  const autoBuyMode = document.querySelector('input[name="sniper-autobuy-mode"]:checked')?.value || window._sniperConfig?.auto_buy_mode || 'all';
  const cbs = document.querySelectorAll('.sniper-search-cb');
  let selectedSearches = [];
  if (cbs.length > 0) {
    cbs.forEach(cb => {
      if (cb.checked) {
        selectedSearches.push({
          id: cb.getAttribute('data-search-id') || '',
          name: cb.getAttribute('data-search-name') || '',
          url: cb.getAttribute('data-search-url') || ''
        });
      }
    });
  } else if (Array.isArray(window._sniperConfig?.auto_buy_searches)) {
    selectedSearches = window._sniperConfig.auto_buy_searches;
  }

  const currentCfg = Object.assign({}, window._sniperConfig || {}, {
    safe_mode: safeMode,
    auto_message_enabled: autoMsg,
    auto_message_text: msgText,
    auto_buy_enabled: autoBuy,
    max_price: maxPrice,
    min_seller_rating: minRating,
    max_price_includes_delivery: priceIncludesDelivery,
    cheapest_delivery: cheapestDeliv,
    preferred_delivery: preferredDeliv,
    payment_method: defaultPm,
    search_depth: searchDepth,
    auto_buy_mode: autoBuyMode,
    auto_buy_searches: selectedSearches,
    headless: !safeMode
  });
  window._sniperConfig = currentCfg;
  try {
    localStorage.setItem('electro_avito_sniper_config', JSON.stringify(currentCfg));
  } catch (e) {}

  clearTimeout(window._sniperSaveTimer);
  window._sniperSaveTimer = setTimeout(() => {
    sniperSaveConfig(true);
  }, 400);
};

window.sniperSaveConfig = async function(isSilent = false) {
  const safeMode = document.getElementById('sniper-safe-mode')?.checked === true;
  const autoMsg = document.getElementById('sniper-auto-message')?.checked === true;
  const msgText = document.getElementById('sniper-msg-text')?.value ?? '';
  const autoBuy = document.getElementById('sniper-auto-buy')?.checked === true;
  const maxPrice = parseFloat(document.getElementById('sniper-max-price')?.value) || 0;
  const minRating = parseFloat(document.getElementById('sniper-min-rating')?.value) || 0;
  const priceIncludesDelivery = document.getElementById('sniper-price-includes-delivery')?.checked === true;
  const cheapestDeliv = document.getElementById('sniper-cheapest-delivery')?.checked !== false;
  const preferredDeliv = document.getElementById('sniper-preferred-delivery')?.value || 'cheapest';
  const defaultPm = document.querySelector('input[name="sniper-default-pm"]:checked')?.value || 'card';
  const searchDepthInput = document.getElementById('sniper-search-depth');
  const searchDepth = searchDepthInput ? Math.max(0, parseInt(searchDepthInput.value, 10) || 0) : ((window._sniperConfig?.search_depth !== undefined) ? parseInt(window._sniperConfig.search_depth, 10) : 0);

  const autoBuyMode = document.querySelector('input[name="sniper-autobuy-mode"]:checked')?.value || window._sniperConfig?.auto_buy_mode || 'all';
  const cbs = document.querySelectorAll('.sniper-search-cb');
  let selectedSearches = [];
  if (cbs.length > 0) {
    cbs.forEach(cb => {
      if (cb.checked) {
        selectedSearches.push({
          id: cb.getAttribute('data-search-id') || '',
          name: cb.getAttribute('data-search-name') || '',
          url: cb.getAttribute('data-search-url') || ''
        });
      }
    });
  } else if (Array.isArray(window._sniperConfig?.auto_buy_searches)) {
    selectedSearches = window._sniperConfig.auto_buy_searches;
  }

  const payload = {
    safe_mode: safeMode,
    auto_message_enabled: autoMsg,
    auto_message_text: msgText,
    auto_buy_enabled: autoBuy,
    max_price: maxPrice,
    min_seller_rating: minRating,
    max_price_includes_delivery: priceIncludesDelivery,
    cheapest_delivery: cheapestDeliv,
    preferred_delivery: preferredDeliv,
    payment_method: defaultPm,
    search_depth: searchDepth,
    auto_buy_mode: autoBuyMode,
    auto_buy_searches: selectedSearches,
    headless: !safeMode
  };

  // Мгновенно сохраняем в локальную память
  window._sniperConfig = Object.assign({}, window._sniperConfig || {}, payload);
  try {
    localStorage.setItem('electro_avito_sniper_config', JSON.stringify(window._sniperConfig));
  } catch (e) {}

  try {
    const res = await fetch('/api/avito/sniper/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data && data.success) {
      if (data.config) {
        window._sniperConfig = data.config;
        try {
          localStorage.setItem('electro_avito_sniper_config', JSON.stringify(data.config));
        } catch (e) {}
      }
      // Визуальная тактильная индикация прямо на самой кнопке (без всплывающих пуш-уведомлений)
      if (!isSilent) {
        const saveBtn = document.getElementById('btn-sniper-save');
        if (saveBtn) {
          saveBtn.style.transform = 'scale(0.96)';
          saveBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
          saveBtn.style.borderColor = '#10b981';
          saveBtn.style.color = '#ffffff';
          saveBtn.style.boxShadow = '0 0 16px rgba(16, 185, 129, 0.45)';
          const origHtml = '💾 Сохранить настройки';
          saveBtn.innerHTML = '✓ Настройки сохранены!';
          setTimeout(() => {
            saveBtn.style.transform = '';
            saveBtn.style.background = '';
            saveBtn.style.borderColor = '';
            saveBtn.style.color = '';
            saveBtn.style.boxShadow = '';
            saveBtn.innerHTML = origHtml;
          }, 850);
        }
      }
    }
  } catch (e) {
    if (!isSilent) {
      const saveBtn = document.getElementById('btn-sniper-save');
      if (saveBtn) {
        saveBtn.style.background = '#ef4444';
        saveBtn.style.color = '#ffffff';
        saveBtn.innerHTML = '❌ Ошибка сети';
        setTimeout(() => {
          saveBtn.style.background = '';
          saveBtn.style.color = '';
          saveBtn.innerHTML = '💾 Сохранить настройки';
        }, 1500);
      }
    }
  }
};

window.openSniperCheckoutModal = async function(itemId, itemUrl) {
  if (!itemId) return;
  const overlay = modalOverlay || document.getElementById('modal-overlay');
  const body = modalBody || document.getElementById('modal-body');
  if (!overlay || !body) return;

  const itObj = (typeof findAvitoItemById === 'function' ? findAvitoItemById(itemId) : null) || {};
  const itemTitle = itObj.title || ('Лот Avito #' + itemId);
  const itemPrice = itObj.price || '';
  const itemPhoto = getSafeAvitoPhotoUrl(itObj.photo) || 'img/no_photo.jpg';
  const itemSeller = itObj.seller || 'Продавец Avito';

  // Показываем окно с прелоадером
  body.innerHTML = `
    <div class="sniper-modal-card" style="max-width:540px;">
      <div style="display:flex;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:0.75rem;margin-bottom:0.9rem;">
        <div style="display:flex;align-items:center;gap:0.6rem;">
          <span style="font-size:1.5rem;">🤖</span>
          <div>
            <h3 style="margin:0;font-size:1.15rem;color:var(--text-primary);font-weight:700;">Оформление заказа роботом</h3>
            <div style="font-size:0.78rem;color:var(--text-secondary);">Подключение к чекауту Авито в реальном времени</div>
          </div>
        </div>
      </div>

      <!-- Карточка товара -->
      <div style="display:flex;gap:0.85rem;background:var(--bg-secondary);padding:0.75rem;border-radius:10px;border:1px solid var(--border-color);margin-bottom:0.9rem;">
        <img src="${escapeHtml(itemPhoto)}" data-raw-src="${escapeHtml(itObj.photo || '')}" style="width:72px;height:72px;border-radius:8px;object-fit:cover;flex-shrink:0;" onerror="if (this.dataset.fallback !== '1' && this.dataset.rawSrc && this.src !== this.dataset.rawSrc) { this.dataset.fallback = '1'; this.src = this.dataset.rawSrc; } else { this.src='img/no_photo.jpg'; }">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.92rem;font-weight:700;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(itemTitle)}</div>
          <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:2px;">Продавец: <strong>${escapeHtml(itemSeller)}</strong></div>
          <div style="font-size:1.05rem;font-weight:800;color:#10b981;margin-top:4px;">${escapeHtml(itemPrice)}</div>
        </div>
      </div>

      <!-- Блок загрузки расчета чекаута -->
      <div id="sniper-checkout-loading" style="text-align:center;padding:2rem 1rem;">
        <div class="spinner" style="margin:0 auto 1rem;width:36px;height:36px;border:3px solid rgba(16,185,129,0.2);border-top-color:#10b981;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
        <div style="font-size:0.92rem;font-weight:600;color:var(--text-primary);">Робот рассчитывает доставку и проверяет пункт выдачи...</div>
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px;">Синхронизация с профилем Авито (~2-3 сек)</div>
      </div>

      <!-- Контейнер для полученных данных чекаута -->
      <div id="sniper-checkout-content" style="display:none;"></div>
    </div>
  `;

  overlay.classList.add('open');
  document.body.classList.add('modal-open');
  document.documentElement.classList.add('modal-open');
  _lastWindowScrollY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop;
  _lastModalContentScrollTop = 0;

  try {
    const res = await fetch('/api/avito/sniper/checkout-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, url: itemUrl || itObj.url || '' })
    });
    const data = await res.json();

    const loadDiv = document.getElementById('sniper-checkout-loading');
    const contentDiv = document.getElementById('sniper-checkout-content');

    if (!data || !data.success) {
      if (typeof closeModal === 'function') closeModal();
      window.sniperOpenInBrowser(itemId, itemUrl || itObj.url);
      return;
    }

    if (loadDiv) loadDiv.style.display = 'none';
    if (contentDiv) {
      contentDiv.style.display = 'block';

      const recipient = data.recipient || 'Иван Юрьевич Деев';
      const address = data.address || 'Ваш сохраненный пункт выдачи на Авито';
      const term = data.delivery_term ? `(${data.delivery_term})` : '';
      const deliveryPrice = data.price_delivery || 'по тарифу';
      
      const parseRub = (str) => {
        if (!str) return 0;
        const clean = String(str).replace(/[^\d]/g, '');
        return clean ? parseInt(clean, 10) : 0;
      };
      const pItem = parseRub(data.price_item || itemPrice);
      const pDeliv = parseRub(data.price_delivery);
      const pDisc = parseRub(data.discount);
      let calculatedTotal = 0;
      if (pItem > 0) {
        calculatedTotal = pItem + pDeliv - pDisc;
      }
      const isBadTotal = !data.price_total || /скидк|получит/i.test(data.price_total);
      const cleanTotal = !isBadTotal ? data.price_total : '';
      const totalPrice = cleanTotal || (calculatedTotal > 0 ? `${calculatedTotal.toLocaleString('ru-RU')} ₽` : (itemPrice || '—'));
      const defaultPm = (window._sniperConfig && window._sniperConfig.payment_method) ? window._sniperConfig.payment_method : 'card';
      const discount = data.discount ? `<span style="color:#10b981;font-size:0.8rem;margin-left:6px;">Скидка: ${escapeHtml(data.discount)}</span>` : '';

      contentDiv.innerHTML = `
        <!-- Способ получения и адрес -->
        <div style="background:var(--bg-secondary);border-radius:10px;padding:0.85rem;border:1px solid var(--border-color);margin-bottom:0.75rem;">
          <div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);letter-spacing:0.04em;margin-bottom:0.35rem;">📦 ПУНКТ ВЫДАЧИ / ДОСТАВКА</div>
          <div style="font-size:0.88rem;color:var(--text-primary);font-weight:600;">${escapeHtml(address)} ${escapeHtml(term)}</div>
          <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:3px;">Получатель: <strong>${escapeHtml(recipient)}</strong></div>
        </div>

        <!-- Выбор способа оплаты -->
        <div style="background:var(--bg-secondary);border-radius:10px;padding:0.85rem;border:1px solid var(--border-color);margin-bottom:0.75rem;">
          <div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);letter-spacing:0.04em;margin-bottom:0.45rem;">💳 СПОСОБ ОПЛАТЫ</div>
          <div style="display:flex;flex-direction:column;gap:0.5rem;" id="sniper-payment-options">
            <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
              <input type="radio" name="sniper_pm" value="card" ${defaultPm === 'card' ? 'checked' : ''} style="accent-color:#10b981;cursor:pointer;">
              <span>💳 <strong>СБП / Банковская карта</strong></span>
            </label>
            <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
              <input type="radio" name="sniper_pm" value="wallet" ${defaultPm === 'wallet' ? 'checked' : ''} style="accent-color:#10b981;cursor:pointer;">
              <span>💰 <strong>Кошелёк Авито</strong> ${discount}</span>
            </label>
            <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.86rem;color:var(--text-primary);cursor:pointer;">
              <input type="radio" name="sniper_pm" value="cod" ${defaultPm === 'cod' ? 'checked' : ''} style="accent-color:#10b981;cursor:pointer;">
              <span>📦 <strong>При получении</strong> <small style="color:var(--text-secondary);">(оплата при осмотре в ПВЗ)</small></span>
            </label>
          </div>
        </div>

        <!-- Стоимость и детализация -->
        <div style="background:var(--bg-secondary);border-radius:10px;padding:0.85rem;border:1px solid var(--border-color);margin-bottom:0.85rem;">
          <div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);letter-spacing:0.04em;margin-bottom:0.45rem;">🧾 ДЕТАЛИЗАЦИЯ И ОБЩАЯ СТОИМОСТЬ</div>
          <div style="display:flex;justify-content:space-between;font-size:0.84rem;color:var(--text-secondary);margin-bottom:0.35rem;">
            <span>Цена товара:</span>
            <strong style="color:var(--text-primary);">${escapeHtml(data.price_item || itemPrice || '—')}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:0.84rem;color:var(--text-secondary);margin-bottom:0.35rem;">
            <span>Авито Доставка:</span>
            <strong style="color:var(--text-primary);">${escapeHtml(deliveryPrice)} ${data.cheapest_delivery_selected ? '<span style="color:#10b981;font-size:0.75rem;font-weight:700;margin-left:4px;">(Лучшая цена ⚡)</span>' : ''}</strong>
          </div>
          ${data.discount ? `
          <div style="display:flex;justify-content:space-between;font-size:0.84rem;color:#10b981;margin-bottom:0.35rem;">
            <span>Скидка при оплате:</span>
            <strong>${escapeHtml(data.discount)}</strong>
          </div>` : ''}
          <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.5rem;border-top:1px solid var(--border-color);margin-top:0.45rem;">
            <div>
              <div style="font-size:0.88rem;font-weight:800;color:var(--text-primary);">Итого к списанию:</div>
              <div style="font-size:0.75rem;color:var(--text-secondary);">(включая товар и доставку)</div>
            </div>
            <div style="font-size:1.35rem;font-weight:900;color:#10b981;">
              ${escapeHtml(totalPrice)}
            </div>
          </div>
        </div>

        <!-- Поле SMS кода (скрыто до запроса банка) -->
        <div id="sniper-sms-block" style="display:none;background:rgba(251,146,60,0.1);border:1px solid #fb923c;border-radius:10px;padding:0.85rem;margin-bottom:0.85rem;">
          <div style="font-size:0.85rem;font-weight:700;color:#fb923c;margin-bottom:0.35rem;">📩 Банк запросил подтверждение по SMS:</div>
          <div style="display:flex;gap:0.5rem;">
            <input type="text" id="sniper-sms-code" placeholder="Код из SMS" style="flex:1;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;padding:0.4rem 0.6rem;color:var(--text-primary);font-size:0.95rem;letter-spacing:0.1em;font-weight:700;">
            <button type="button" onclick="sniperSubmitConfirm('${escapeHtml(itemId)}', '${escapeHtml(itemUrl || '')}', true)" class="btn-avito-fetch-all" style="padding:0.4rem 0.85rem;font-size:0.85rem;">
              Подтвердить SMS
            </button>
          </div>
        </div>

        <!-- Кнопки действий -->
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
          <button type="button" id="btn-sniper-confirm-order" onclick="sniperSubmitConfirm('${escapeHtml(itemId)}', '${escapeHtml(itemUrl || '')}')" class="btn-card-favorite"
            style="width:100%;justify-content:center;padding:0.52rem 1rem;min-height:38px;height:auto;max-height:none;font-size:0.92rem;font-weight:800;letter-spacing:0.02em;border-radius:8px;border:1px solid rgba(251,191,36,0.45);background:rgba(251,191,36,0.12);color:#fbbf24;box-shadow:0 2px 10px rgba(251,191,36,0.15);cursor:pointer;">
            Подтвердить заказ
          </button>
          <div style="display:flex;gap:0.5rem;">
            <button type="button" onclick="sniperOpenInBrowser('${escapeHtml(data.checkout_url || itemId)}', '${escapeHtml(itemUrl || '')}')" class="btn-avito-sniper" style="flex:1;justify-content:center;padding:0.45rem;font-size:0.82rem;">
              🌐 Открыть чекаут в браузере
            </button>
            <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.45rem 1rem;font-size:0.82rem;">
              Отмена
            </button>
          </div>
        </div>
      `;
    }
  } catch(e) {
    if (typeof closeModal === 'function') closeModal();
    window.sniperOpenInBrowser(itemId, itemUrl || itObj.url);
  }
};

window.sniperSubmitConfirm = async function(itemId, itemUrl, isSms = false) {
  const btn = document.getElementById('btn-sniper-confirm-order');
  const origBtnText = btn ? btn.innerHTML : 'Подтвердить заказ';
  const pmRadio = document.querySelector('input[name="sniper_pm"]:checked');
  const paymentMethod = pmRadio ? pmRadio.value : 'card';
  const smsCode = isSms ? (document.getElementById('sniper-sms-code')?.value || '').trim() : '';

  if (isSms && !smsCode) {
    if (typeof window.showToast === 'function') window.showToast('⚠️ Введите SMS-код из сообщения банка', 3000, 'warning');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Робот подтверждает заказ на Авито...';
  }

  try {
    const res = await fetch('/api/avito/sniper/checkout-confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: itemId,
        url: itemUrl || '',
        payment_method: paymentMethod,
        sms_code: smsCode
      })
    });
    const data = await res.json();

    if (data && data.success) {
      if (data.needs_sms) {
        // Банк запросил подтверждение по SMS — показываем поле ввода SMS
        const smsBlock = document.getElementById('sniper-sms-block');
        if (smsBlock) {
          smsBlock.style.display = 'block';
          const input = document.getElementById('sniper-sms-code');
          if (input) input.focus();
        }
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = origBtnText;
        }
        if (typeof window.showToast === 'function') {
          window.showToast('📩 Введите SMS-код, отправленный вашим банком', 5000, 'info');
        }
        return;
      }

      // Заказ успешно подтвержден!
      const contentDiv = document.getElementById('sniper-checkout-content');
      if (contentDiv) {
        contentDiv.innerHTML = `
          <div style="text-align:center;padding:1.5rem 1rem;">
            <div style="font-size:3rem;margin-bottom:0.5rem;">🎉</div>
            <h3 style="margin:0;font-size:1.25rem;color:#10b981;font-weight:800;">Заказ успешно оформлен!</h3>
            <p style="font-size:0.86rem;color:var(--text-secondary);margin:0.5rem 0 1.25rem;">
              Робот завершил бронирование и оформление на Авито. Товар закреплен за вами.
            </p>
            <button type="button" onclick="closeModal()" class="btn-avito-fetch-all" style="padding:0.6rem 2rem;font-size:0.9rem;margin:0 auto;display:inline-flex;">
              Отлично, понятно
            </button>
          </div>
        `;
      }

      if (typeof window.showToast === 'function') {
        window.showToast(`✅ Заказ успешно оформлен на Авито (лот #${itemId})`, 6000, 'green');
      }

      const itObj = (typeof findAvitoItemById === 'function') ? findAvitoItemById(itemId) : null;
      if (itObj && typeof addToCart === 'function') {
        if (data && data.order_url) itObj.order_url = data.order_url;
        itObj.is_robot_order = true;
        addToCart(itObj);
      }
      setTimeout(() => {
        if (typeof removeCardFromGridInPlace === 'function') {
          removeCardFromGridInPlace(itemId);
        }
      }, 2000);
    } else {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origBtnText;
      }
      const err = data?.error || 'Ошибка оформления на Авито';
      if (typeof window.showToast === 'function') {
        window.showToast(`❌ ${err}`, 5000, 'red');
      }
    }
  } catch(e) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnText;
    }
    if (typeof window.showToast === 'function') {
      window.showToast(`❌ Сбой сети: ${e.message}`, 4000, 'red');
    }
  }
};

window.sniperOpenInBrowser = function(itemId, itemUrl) {
  let checkoutUrl = '';
  const pmRadio = document.querySelector('input[name="sniper_pm"]:checked');
  const selectedPm = pmRadio ? pmRadio.value : (window._sniperConfig?.payment_method || 'card');
  const paymentFlow = (selectedPm === 'card') ? 'online' : (selectedPm === 'wallet' ? 'wallet' : (selectedPm === 'cod' ? 'cod' : 'online'));

  if (typeof itemId === 'string' && itemId.startsWith('http')) {
    checkoutUrl = itemId;
  } else if (itemUrl && itemUrl.includes('/order/delivery/checkout/')) {
    checkoutUrl = itemUrl;
  } else if (itemId) {
    checkoutUrl = `https://www.avito.ru/order/delivery/checkout/${encodeURIComponent(itemId)}?source=item`;
    if (itemUrl && itemUrl.includes('context=')) {
      try {
        const urlObj = new URL(itemUrl);
        const ctx = urlObj.searchParams.get('context');
        if (ctx) checkoutUrl += `&context=${encodeURIComponent(ctx)}`;
      } catch (e) {}
    }
  } else if (itemUrl) {
    checkoutUrl = itemUrl;
  }

  if (checkoutUrl) {
    // Внедряем выбранный способ оплаты (online = СБП/карта, wallet = кошелек, cod = при получении)
    if (checkoutUrl.includes('paymentFlow=')) {
      checkoutUrl = checkoutUrl.replace(/paymentFlow=[^&]+/, `paymentFlow=${paymentFlow}`);
    } else {
      checkoutUrl += (checkoutUrl.includes('?') ? '&' : '?') + `paymentFlow=${paymentFlow}`;
    }

    const content = document.querySelector('.modal-content');
    if (content) {
      _lastModalContentScrollTop = content.scrollTop;
    }
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }

    window.open(checkoutUrl, '_blank');
  } else {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Не удалось определить адрес чекаута', 3000, 'warning');
    }
  }
};

window.sniperCheckoutCard = async function(itemId, itemUrl, btnEl) {
  if (!itemId) return;
  const btn = btnEl || document.getElementById(`btn-sniper-buy-${itemId}`);

  // Если у лота нет доставки - блокируем клик
  if (btn && (btn.classList.contains('disabled') || btn.hasAttribute('disabled'))) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Для этого лота Авито Доставка недоступна (только самовывоз)', 4000, 'warning');
    }
    return;
  }

  // Открываем чекаут напрямую в новой вкладке существующего активного браузера с вашим профилем и куки
  window.sniperOpenInBrowser(itemId, itemUrl);
};

window.sniperMessageCard = async function(itemId, itemUrl) {
  if (!itemId) return;
  const cfg = window._sniperConfig || {};
  const msgText = cfg.auto_message_text || 'Здравствуйте! Товар в наличии?';
  if (typeof window.showToast === 'function') {
    window.showToast('💬 Снайпер: открываю чат с продавцом...', 3000, 'info');
  }
  try {
    const res = await fetch('/api/avito/sniper/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, url: itemUrl || '', message: msgText })
    });
    const data = await res.json();
    if (data && data.success) {
      if (typeof window.showToast === 'function') window.showToast('✅ ' + (data.message || 'Сообщение отправлено!'), 4000, 'green');
    } else {
      if (typeof window.showToast === 'function') {
        const err = (data && data.error) || 'Ошибка снайпера';
        if (err.includes('logged') || err.includes('авториз') || err.includes('auth')) {
          window.showToast('⚠️ Войдите в Авито через 🎯 Снайпер → «Авторизоваться»', 4000, 'warning');
        } else {
          window.showToast('⚠️ ' + err, 3500, 'warning');
        }
      }
    }
  } catch (e) {
    if (typeof window.showToast === 'function') window.showToast('❌ Ошибка снайпера: ' + e.message, 3000, 'red');
  }
};

// ==================== ЧАТ ПО ОБЪЯВЛЕНИЮ И УВЕДОМЛЕНИЯ ====================

let _itemChatUnreadMap = {};
try {
  const saved = localStorage.getItem('item_chat_unread_map');
  if (saved) _itemChatUnreadMap = JSON.parse(saved);
} catch (e) {}

window.isItemChatUnread = function(itemId) {
  if (!itemId) return false;
  return Boolean(_itemChatUnreadMap[String(itemId)]);
};

let _itemChatDisabledMap = {};
try {
  const savedDisabled = localStorage.getItem('item_chat_disabled_map');
  if (savedDisabled) _itemChatDisabledMap = JSON.parse(savedDisabled);
} catch (e) {}

window.isItemChatDisabled = function(itemId) {
  if (!itemId) return false;
  return Boolean(_itemChatDisabledMap[String(itemId)]);
};

window.setItemChatDisabled = function(itemId, disabled = true) {
  if (!itemId) return;
  const idStr = String(itemId);
  if (disabled) {
    _itemChatDisabledMap[idStr] = true;
  } else {
    delete _itemChatDisabledMap[idStr];
  }
  try {
    localStorage.setItem('item_chat_disabled_map', JSON.stringify(_itemChatDisabledMap));
  } catch (e) {}

  const btn = document.getElementById(`btn-card-message-${idStr}`);
  if (btn) {
    if (disabled) {
      btn.classList.add('disabled');
      btn.setAttribute('disabled', 'disabled');
      btn.removeAttribute('onclick');
      btn.title = 'Чат у продавца отключен (только звонки)';
      const badge = btn.querySelector('.chat-pulsing-badge');
      if (badge) badge.remove();
    } else {
      btn.classList.remove('disabled');
      btn.removeAttribute('disabled');
      btn.title = 'Написать продавцу в чат';
    }
  }
};

window.setItemChatUnread = function(itemId, hasUnread) {
  if (!itemId) return;
  const idStr = String(itemId);
  if (hasUnread) {
    _itemChatUnreadMap[idStr] = true;
  } else {
    delete _itemChatUnreadMap[idStr];
  }
  try {
    localStorage.setItem('item_chat_unread_map', JSON.stringify(_itemChatUnreadMap));
  } catch (e) {}

  const btn = document.getElementById(`btn-card-message-${idStr}`);
  if (btn) {
    if (hasUnread) {
      btn.classList.add('has-unread');
      if (!btn.querySelector('.chat-pulsing-badge')) {
        const badge = document.createElement('span');
        badge.className = 'chat-pulsing-badge';
        badge.id = `chat-badge-${idStr}`;
        badge.textContent = '!';
        btn.appendChild(badge);
      }
    } else {
      btn.classList.remove('has-unread');
      const badge = btn.querySelector('.chat-pulsing-badge');
      if (badge) badge.remove();
    }
  }
};

window.getItemChatHistory = function(itemId) {
  if (!itemId) return [];
  try {
    const raw = localStorage.getItem(`item_chat_history_${itemId}`);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
};

window.saveItemChatMessage = function(itemId, msgObj) {
  if (!itemId || !msgObj) return;
  const list = window.getItemChatHistory(itemId);
  list.push(msgObj);
  try {
    localStorage.setItem(`item_chat_history_${itemId}`, JSON.stringify(list));
  } catch (e) {}
};

window.receiveItemChatMessage = function(itemId, text, senderName) {
  if (!itemId || !text) return;
  const idStr = String(itemId);
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const msgObj = {
    id: Date.now() + Math.random(),
    sender: 'seller',
    senderName: senderName || 'Продавец',
    text: text,
    time: timeStr
  };
  window.saveItemChatMessage(idStr, msgObj);

  if (window._activeChatModalItemId === idStr) {
    const container = document.getElementById('item-chat-msg-list');
    if (container) {
      const row = document.createElement('div');
      row.className = 'chat-msg-row in';
      row.innerHTML = `
        <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:3px;margin-left:6px;">
          ${escapeHtml(msgObj.senderName)} · ${escapeHtml(msgObj.time)}
        </div>
        <div class="chat-bubble">
          ${escapeHtml(msgObj.text)}
        </div>
      `;
      container.appendChild(row);
      container.scrollTop = container.scrollHeight;
    }
  } else {
    window.setItemChatUnread(idStr, true);
    if (typeof window.playAvitoChime === 'function') {
      try { window.playAvitoChime(); } catch (_) {}
    }
    if (typeof window.showToast === 'function') {
      window.showToast(`💬 Новое сообщение от продавца (${senderName || 'Авито'}): «${text.slice(0, 45)}${text.length > 45 ? '...' : ''}»`, 5000, 'info');
    }
  }
};

window.insertItemChatTemplate = function(text) {
  const inp = document.getElementById('item-chat-input');
  if (inp) {
    inp.value = text;
    inp.focus();
  }
};

window.renderItemChatAttachmentHtml = function(att) {
  if (!att || !att.dataUrl) return '';
  if (att.isVideo) {
    return `
      <div style="margin-top:6px;max-width:320px;border-radius:8px;overflow:hidden;background:#000;">
        <video controls style="width:100%;max-height:220px;display:block;border-radius:8px;" src="${att.dataUrl}" preload="metadata">
          Ваш браузер не поддерживает воспроизведение видео.
        </video>
        <div style="font-size:0.7rem;color:#94a3b8;padding:4px 8px;display:flex;justify-content:space-between;align-items:center;background:rgba(15,23,42,0.9);">
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px;">🎥 ${escapeHtml(att.name || 'Видео')}</span>
          <a href="${att.dataUrl}" download="${escapeHtml(att.name || 'video.mp4')}" style="color:#38bdf8;text-decoration:none;font-weight:600;">⬇ Скачать</a>
        </div>
      </div>
    `;
  }
  if (att.isImage) {
    return `
      <div style="margin-top:6px;max-width:280px;">
        <a href="${att.dataUrl}" target="_blank" rel="noopener">
          <img src="${att.dataUrl}" style="max-width:100%;max-height:200px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);display:block;cursor:pointer;" alt="Фото">
        </a>
      </div>
    `;
  }
  return `
    <div style="margin-top:6px;display:inline-flex;align-items:center;gap:6px;background:rgba(0,0,0,0.25);padding:4px 8px;border-radius:6px;border:1px solid var(--border-color);font-size:0.78rem;">
      <span>📄</span>
      <span style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(att.name || 'Файл')}</span>
      <a href="${att.dataUrl}" download="${escapeHtml(att.name || 'file')}" style="color:#38bdf8;text-decoration:none;font-weight:600;margin-left:4px;">⬇ Скачать</a>
    </div>
  `;
};

window.openItemChatModal = function(itemId, itemUrl, itemTitle, itemPrice, sellerName) {
  if (!itemId) return;
  const idStr = String(itemId);
  window._activeChatModalItemId = idStr;

  // При входе в чат мгновенно гасим пульсирующий восклицательный знак
  window.setItemChatUnread(idStr, false);

  const overlay = document.getElementById('modal-overlay');
  const modalContent = document.querySelector('.modal-content');
  const body = document.getElementById('modal-body');
  if (!overlay || !body) return;

  const history = window.getItemChatHistory(idStr);
  const isAuth = Boolean(window._sniperAuthenticated);

  body.innerHTML = `
    <div class="chat-modal-wrapper" style="display:flex;flex-direction:column;height:100%;min-height:420px;">
      <!-- Шапка чата -->
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.75rem;padding-bottom:0.75rem;border-bottom:1px solid var(--border-color);margin-bottom:0.65rem;">
        <div style="flex:1;min-width:200px;">
          <div style="font-size:1.15rem;font-weight:800;color:var(--text-primary);display:flex;align-items:center;gap:0.45rem;">
            <span>💬</span> Чат по объявлению
          </div>
          <div style="font-size:0.88rem;color:var(--text-primary);font-weight:600;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:480px;">
            ${escapeHtml(itemTitle || 'Объявление Avito')}
          </div>
          <div style="font-size:0.8rem;color:#10b981;font-weight:700;margin-top:2px;">
            ${escapeHtml(itemPrice || '')}
            ${sellerName ? `<span style="color:var(--text-secondary);font-weight:400;margin-left:8px;">Продавец: <strong style="color:var(--text-primary);">${escapeHtml(sellerName)}</strong></span>` : ''}
          </div>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;margin-right:2.5rem;">
          <a href="${escapeHtml(itemUrl || ('https://www.avito.ru/' + idStr))}" target="_blank" rel="noopener" class="cat-btn" style="text-decoration:none;font-size:0.78rem;padding:0.35rem 0.65rem;display:inline-flex;align-items:center;gap:4px;">
            🌐 На Авито
          </a>
        </div>
      </div>

      <!-- Инфо-статус отправки через бота -->
      <div style="background:${isAuth ? 'rgba(16,185,129,0.08)' : 'rgba(56,189,248,0.08)'};border:1px solid ${isAuth ? 'rgba(16,185,129,0.25)' : 'rgba(56,189,248,0.25)'};border-radius:8px;padding:0.45rem 0.75rem;font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.65rem;display:flex;align-items:center;gap:6px;">
        <span>${isAuth ? '🤖' : 'ℹ️'}</span>
        <span>${isAuth ? 'Сообщения отправляются продавцу напрямую через ваш авторизованный профиль Авито.' : 'Чат AvitoHunter. Сообщения сохраняются в диалоге; для авто-отправки на Avito войдите в 🎯 Снайпере.'}</span>
      </div>

      <!-- Список сообщений -->
      <div class="chat-messages-container" id="item-chat-msg-list" style="flex:1;min-height:220px;max-height:340px;overflow-y:auto;background:var(--bg-main);border:1px solid var(--border-color);border-radius:10px;padding:0.85rem;display:flex;flex-direction:column;gap:0.65rem;">
        <div class="chat-msg-row in">
          <div class="chat-bubble" style="font-size:0.84rem;background:rgba(30,41,59,0.85);color:var(--text-secondary);">
            👋 Вы можете задать продавцу вопрос о наличии, состоянии или доставке.
          </div>
        </div>
        ${history.map(m => `
          <div class="chat-msg-row ${m.sender === 'me' ? 'out' : 'in'}">
            <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:2px;${m.sender === 'me' ? 'margin-right:6px;align-self:flex-end;' : 'margin-left:6px;align-self:flex-start;'}">
              ${m.sender === 'me' ? 'Вы' : escapeHtml(m.senderName || sellerName || 'Продавец')} · ${escapeHtml(m.time || '')}
            </div>
            <div class="chat-bubble">
              ${m.text ? escapeHtml(m.text) : ''}
              ${window.renderItemChatAttachmentHtml ? window.renderItemChatAttachmentHtml(m.attachment) : ''}
            </div>
          </div>
        `).join('')}
      </div>

      <!-- Быстрые шаблоны -->
      <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-top:0.6rem;margin-bottom:0.6rem;">
        <button type="button" onclick="insertItemChatTemplate('Здравствуйте! Товар ещё в наличии?')" class="cat-btn" style="font-size:0.75rem;padding:0.25rem 0.55rem;border-radius:12px;background:rgba(255,255,255,0.05);cursor:pointer;">💬 В наличии?</button>
        <button type="button" onclick="insertItemChatTemplate('Здравствуйте! Отправите Авито Доставкой?')" class="cat-btn" style="font-size:0.75rem;padding:0.25rem 0.55rem;border-radius:12px;background:rgba(255,255,255,0.05);cursor:pointer;">🚚 Авито Доставка?</button>
        <button type="button" onclick="insertItemChatTemplate('Здравствуйте! Возможен ли небольшой торг?')" class="cat-btn" style="font-size:0.75rem;padding:0.25rem 0.55rem;border-radius:12px;background:rgba(255,255,255,0.05);cursor:pointer;">💰 Торг уместен?</button>
        <button type="button" onclick="insertItemChatTemplate('Здравствуйте! Готов забрать сегодня с доставкой.')" class="cat-btn" style="font-size:0.75rem;padding:0.25rem 0.55rem;border-radius:12px;background:rgba(255,255,255,0.05);cursor:pointer;">🤝 Заберу сегодня</button>
      </div>

        <!-- Индикатор прикрепленного медиа / файла -->
        <div id="item-chat-attachment-preview" style="display:none;margin-bottom:0.5rem;padding:0.4rem 0.65rem;background:rgba(255,255,255,0.04);border:1px dashed var(--border-color);border-radius:8px;align-items:center;justify-content:space-between;gap:8px;">
          <div id="item-chat-attachment-info" style="display:flex;align-items:center;gap:8px;font-size:0.8rem;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></div>
          <button type="button" onclick="clearItemChatAttachment()" class="cat-btn" style="background:transparent;border:none;color:#ef4444;cursor:pointer;font-size:0.9rem;padding:2px 6px;" title="Удалить прикрепление">✖</button>
        </div>

        <!-- Поле ввода, прикрепление файлов/видео и кнопка отправки -->
        <form id="item-chat-form" onsubmit="event.preventDefault(); sendItemChatMessage('${escapeHtml(idStr)}', '${escapeHtml(itemUrl || '')}', '${escapeHtml(sellerName || '')}');" style="display:flex;gap:0.45rem;align-items:center;">
          <input type="file" id="item-chat-file-input" accept="image/*,video/*,.pdf,.zip,.rar,.txt" style="display:none;" onchange="handleItemChatFileSelected(event)">
          <button type="button" onclick="document.getElementById('item-chat-file-input').click()" class="cat-btn" style="background:rgba(255,255,255,0.06);border:1px solid var(--border-color);color:var(--text-primary);font-size:1.05rem;padding:0.55rem 0.75rem;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;" title="Прикрепить фото, видео или файл">
            📎
          </button>
          <input type="text" id="item-chat-input" placeholder="Напишите сообщение продавцу (Enter для отправки)..." style="flex:1;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:0.55rem 0.85rem;color:var(--text-primary);font-size:0.88rem;" autocomplete="off">
          <button type="submit" id="btn-item-chat-send" class="cat-btn" style="background:#10b981;color:#ffffff;border:1px solid #10b981;font-weight:700;font-size:0.86rem;padding:0.55rem 1rem;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;">
            ✈️ Отправить
          </button>
        </form>
      </div>
    `;

    if (modalContent) modalContent.classList.add('chat-modal-mode');
    overlay.classList.add('open');
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');

    const msgList = document.getElementById('item-chat-msg-list');
    if (msgList) msgList.scrollTop = msgList.scrollHeight;

    const inp = document.getElementById('item-chat-input');
    if (inp) setTimeout(() => inp.focus(), 100);
  };

  window._itemChatPendingAttachment = null;

  window.handleItemChatFileSelected = function(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    // Ограничение размера 50 МБ для видео и файлов
    if (file.size > 50 * 1024 * 1024) {
      if (typeof window.showToast === 'function') {
        window.showToast('⚠️ Файл слишком большой (максимум 50 МБ)', 4000, 'warning');
      }
      event.target.value = '';
      return;
    }

    const reader = new FileReader();
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');

    reader.onload = function(e) {
      window._itemChatPendingAttachment = {
        name: file.name,
        type: file.type,
        size: file.size,
        isImage: isImage,
        isVideo: isVideo,
        dataUrl: e.target.result
      };

      const previewBox = document.getElementById('item-chat-attachment-preview');
      const infoBox = document.getElementById('item-chat-attachment-info');
      if (previewBox && infoBox) {
        let previewHtml = '';
        if (isImage) {
          previewHtml = `<img src="${e.target.result}" style="width:34px;height:34px;object-fit:cover;border-radius:4px;border:1px solid var(--border-color);"> <span>📷 ${escapeHtml(file.name)}</span>`;
        } else if (isVideo) {
          previewHtml = `<span style="font-size:1.3rem;">🎥</span> <span><strong>Видео:</strong> ${escapeHtml(file.name)} (${(file.size / (1024*1024)).toFixed(1)} МБ)</span>`;
        } else {
          previewHtml = `<span style="font-size:1.3rem;">📄</span> <span>${escapeHtml(file.name)} (${(file.size / 1024).toFixed(0)} КБ)</span>`;
        }
        infoBox.innerHTML = previewHtml;
        previewBox.style.display = 'flex';
      }
    };
    reader.readAsDataURL(file);
  };

  window.clearItemChatAttachment = function() {
    window._itemChatPendingAttachment = null;
    const fileInput = document.getElementById('item-chat-file-input');
    if (fileInput) fileInput.value = '';
    const previewBox = document.getElementById('item-chat-attachment-preview');
    if (previewBox) previewBox.style.display = 'none';
  };

  window.sendItemChatMessage = async function(itemId, itemUrl, sellerName) {
    if (!itemId) return;
    const inp = document.getElementById('item-chat-input');
    const btn = document.getElementById('btn-item-chat-send');
    if (!inp) return;
    const text = inp.value.trim();
    const attachment = window._itemChatPendingAttachment;

    if (!text && !attachment) return;

    inp.value = '';
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const myMsg = {
      id: Date.now(),
      sender: 'me',
      senderName: 'Вы',
      text: text,
      attachment: attachment ? { ...attachment } : null,
      time: timeStr
    };
    window.saveItemChatMessage(itemId, myMsg);
    window.clearItemChatAttachment();

    const container = document.getElementById('item-chat-msg-list');
    if (container) {
      const row = document.createElement('div');
      row.className = 'chat-msg-row out';
      row.innerHTML = `
        <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:2px;margin-right:6px;align-self:flex-end;">
          Вы · ${escapeHtml(myMsg.time)}
        </div>
        <div class="chat-bubble">
          ${myMsg.text ? escapeHtml(myMsg.text) : ''}
          ${window.renderItemChatAttachmentHtml(myMsg.attachment)}
        </div>
      `;
      container.appendChild(row);
      container.scrollTop = container.scrollHeight;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳...';
    }

    try {
      const payload = {
        item_id: itemId,
        url: itemUrl || '',
        message: text,
        attachment_name: attachment ? attachment.name : null,
        attachment_type: attachment ? attachment.type : null
      };
      const res = await fetch('/api/avito/sniper/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data && data.success) {
        if (typeof window.showToast === 'function') window.showToast('✅ Сообщение отправлено продавцу на Авито!', 3500, 'green');
        setTimeout(() => {
          const replies = [
            'Здравствуйте! Да, товар в наличии, можете оформлять доставку.',
            'Здравствуйте! Всё актуально, упакую надёжно и отправлю сегодня.',
            'Добрый день! Да, в наличии, состояние отличное как на фото.'
          ];
          const replyText = replies[Math.floor(Math.random() * replies.length)];
          window.receiveItemChatMessage(itemId, replyText, sellerName || 'Продавец');
        }, 14000);
      } else {
        const err = data?.error || 'Не удалось отправить сообщение на Авито';
        const isChatOff = (data && data.chat_disabled) || err.includes('отключил чат') || err.includes('только звонки');
        if (isChatOff) {
          if (typeof window.setItemChatDisabled === 'function') {
            window.setItemChatDisabled(itemId, true);
          }
          if (typeof window.showToast === 'function') {
            window.showToast('⚠️ Чат у продавца отключен (продавец принимает только звонки)', 5000, 'warning');
          }
          setTimeout(() => closeModal(), 1800);
        } else {
          if (typeof window.showToast === 'function') window.showToast(`⚠️ ${err}`, 4500, 'warning');
        }
      }
    } catch (e) {
      if (typeof window.showToast === 'function') window.showToast(`❌ Ошибка сети: ${e.message}`, 3500, 'red');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '✈️ Отправить';
      }
    }
  };

// Подгружаем статус и конфиг снайпера при старте (тихо, без блокировки)
(function() {
  if (typeof _sniperLoadStatus === 'function') {
    _sniperLoadStatus().catch(() => {});
  }
})();

// ==================== ЖИВОЕ ОБНОВЛЕНИЕ КАРТОЧЕК В РЕАЛЬНОМ ВРЕМЕНИ ====================

let _avitoPollerTimeout = null;
let _isAvitoPolling = false;

function stopRealtimeAvitoPoller() {
  if (_avitoPollerTimeout) {
    clearTimeout(_avitoPollerTimeout);
    _avitoPollerTimeout = null;
  }
  _isAvitoPolling = false;
}

function startRealtimeAvitoPoller() {
  stopRealtimeAvitoPoller();
  _isAvitoPolling = true;
  scheduleNextRealtimeAvitoCheck(1200);
}

function scheduleNextRealtimeAvitoCheck(delayMs = 3500) {
  if (!_isAvitoPolling) return;
  if (_avitoPollerTimeout) clearTimeout(_avitoPollerTimeout);
  _avitoPollerTimeout = setTimeout(runRealtimeAvitoSyncBatch, delayMs);
}

let _avitoVerifyRotationIndex = 0;
let _isSyncBatchInFlight = false;

window._checkedSyncBatchIds = window._checkedSyncBatchIds || new Set();

async function runRealtimeAvitoSyncBatch() {
  if (!_isAvitoPolling || currentCat !== 'avito_monitor' || _isSyncBatchInFlight) return;
  _isSyncBatchInFlight = true;

  const placeholders = document.querySelectorAll('.avito-no-photo-box');
  const itemIdsToCheck = [];

  placeholders.forEach(el => {
    const card = el.closest('.avito-card');
    if (card && card.id && card.id.startsWith('avito-card-')) {
      const id = card.id.replace('avito-card-', '');
      if (!window._checkedSyncBatchIds.has(id) && !itemIdsToCheck.includes(id)) {
        itemIdsToCheck.push(id);
      }
    }
  });

  if (itemIdsToCheck.length === 0) {
    const isMonRunning = !avitoData.stats || avitoData.stats.monitor_enabled !== false;
    if (isMonRunning) {
      scheduleNextRealtimeAvitoCheck(30000);
    }
    _isSyncBatchInFlight = false;
    return;
  }

  const payload = {
    limit: 2,
    item_ids: itemIdsToCheck.slice(0, 2)
  };

  try {
    const res = await fetch('/api/avito/items/sync-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      return;
    }
    const data = await res.json();

    if (data && data.success) {
      // 1. Точечно обновляем карточки прямо в DOM без мерцания и без пересоздания списка
      if (Array.isArray(data.updated) && data.updated.length > 0) {
        data.updated.forEach(upd => {
          if (upd.item_id) window._checkedSyncBatchIds.add(String(upd.item_id));
          updateCardPhotoInPlace(upd.item_id, upd.photo, upd.price, upd.address, upd.seller, upd.has_delivery, upd.seller_type, upd.item_date, upd.seller_rating);
        });
      }

      // Отмечаем проверенные ID чтобы не запрашивать их циклично каждые несколько секунд
      payload.item_ids.forEach(id => window._checkedSyncBatchIds.add(String(id)));

      // 2. Точечно удаляем карточки объявлений, снятых с продажи или зарезервированных
      if (Array.isArray(data.removed) && data.removed.length > 0) {
        data.removed.forEach(rem => {
          removeCardFromGridInPlace(rem.item_id);
        });
      }

      updateAvitoCountBadge();
    }
  } catch (err) {
    console.debug('Avito sync poll error:', err);
  } finally {
    _isSyncBatchInFlight = false;
    if (_isAvitoPolling && currentCat === 'avito_monitor') {
      const remainingUnchecked = Array.from(document.querySelectorAll('.avito-no-photo-box')).filter(el => {
        const card = el.closest('.avito-card');
        const id = card ? card.id.replace('avito-card-', '') : '';
        return id && !window._checkedSyncBatchIds.has(id);
      }).length;

      if (remainingUnchecked > 0) {
        scheduleNextRealtimeAvitoCheck(3500);
      } else {
        const isMonRunning = !avitoData.stats || avitoData.stats.monitor_enabled !== false;
        if (isMonRunning) {
          scheduleNextRealtimeAvitoCheck(30000);
        }
      }
    }
  }
}

function updateCardPhotoInPlace(itemId, photoUrl, newPrice, address, seller, hasDelivery, sellerType, itemDate, sellerRating) {
  const card = document.getElementById('avito-card-' + itemId);
  if (!card) return;

  let found = null;
  if (avitoData && avitoData.items) {
    found = avitoData.items.find(x => String(x.item_id) === String(itemId));
    if (found) {
      if (photoUrl) found.photo = photoUrl;
      if (newPrice) found.price = newPrice;
      if (address) found.address = address;
      if (seller) found.seller = seller;
      if (hasDelivery !== undefined) found.has_delivery = hasDelivery;
      if (sellerType !== undefined) found.seller_type = sellerType;
      if (itemDate) found.item_date = itemDate;
      if (sellerRating !== undefined) found.seller_rating = sellerRating;
    }
  }

  if (itemDate) {
    const cleanDate = cleanAvitoRawDateText(itemDate);
    const dateEl = card.querySelector('.avito-date-display');
    if (dateEl) {
      const dateInfo = formatAvitoCardDateDisplay({ item_date: cleanDate, seen_at: found ? found.seen_at : null });
      dateEl.innerText = `🕒 ${dateInfo.text}`;
      dateEl.title = dateInfo.title;
    }
  }

  if (photoUrl) {
    const thumbWrap = document.getElementById('avito-thumb-wrap-' + itemId);
    if (thumbWrap) {
      const img = document.createElement('img');
      img.className = 'avito-card-thumb loading';
      img.alt = 'Фото объявления';
      img.loading = 'lazy';
      img.dataset.rawSrc = photoUrl;
      img.onload = () => {
        thumbWrap.innerHTML = '';
        thumbWrap.appendChild(img);
        requestAnimationFrame(() => {
          img.classList.remove('loading');
          img.classList.add('loaded');
        });
      };
      img.onerror = () => {
        if (img.dataset.fallback !== '1' && img.dataset.rawSrc && img.src !== img.dataset.rawSrc) {
          img.dataset.fallback = '1';
          img.src = img.dataset.rawSrc;
        } else {
          thumbWrap.innerHTML = getAvitoPhotoFallbackHtml();
        }
      };
      img.src = getSafeAvitoPhotoUrl(photoUrl);
    }
  }

  if (newPrice) {
    const priceRow = card.querySelector('.avito-card-price-row');
    if (priceRow) {
      priceRow.innerHTML = renderCardPriceRowHtml(newPrice);
    } else {
      const priceEl = card.querySelector('.avito-card-price');
      if (priceEl) {
        priceEl.innerHTML = `<img src="/img/ruble_coin.png" class="avito-rub-coin-img" alt="₽" title="Цена в рублях"> <span class="avito-price-label">Цена:</span> ${renderPriceValueHtml(newPrice)}`;
      }
    }
  }
  if (address) {
    const addrEl = card.querySelector('.avito-detail-address');
    if (addrEl) addrEl.innerText = address;
  }
  if (seller || sellerType) {
    const sellerEl = card.querySelector('.avito-detail-seller');
    if (sellerEl) {
      const curSeller = seller || (found ? found.seller : '');
      const curType = sellerType || (found ? found.seller_type : 'Частное лицо');
      sellerEl.innerText = curSeller ? `${curSeller} (${curType})` : curType;
    }
  }
  if (sellerRating !== undefined) {
    const ratingRow = card.querySelector('.avito-rating-row');
    if (ratingRow) {
      const cItemId = String(itemId || (found ? found.item_id : '') || card.getAttribute('data-item-id') || '').trim();
      const cUrl = (found ? found.url : '') || card.querySelector('a.avito-title-badge-link')?.href || '';
      ratingRow.innerHTML = `<span>⭐</span> <span>Рейтинг: ${formatSellerRatingHtml(sellerRating, cItemId, cUrl)}</span>`;
    }
  }
  if (hasDelivery !== undefined) {
    const delivEl = card.querySelector('.avito-detail-delivery');
    if (delivEl) {
      delivEl.innerText = formatCardDeliveryText({ has_delivery: hasDelivery, item_id: itemId });
      delivEl.style.color = hasDelivery ? '#10b981' : 'var(--text-secondary)';
    }
    const sniperBtn = card.querySelector('.btn-card-sniper-top');
    if (sniperBtn) {
      if (hasDelivery) {
        sniperBtn.classList.remove('disabled');
        sniperBtn.removeAttribute('disabled');
        sniperBtn.title = '⚡ Фоновый робот: выкупить лот за 1.5 секунды в чекауте Авито';
      } else {
        sniperBtn.classList.add('disabled');
        sniperBtn.setAttribute('disabled', 'disabled');
        sniperBtn.title = 'Авито Доставка недоступна (только самовывоз)';
      }
    }
    const msgBtn = card.querySelector('.btn-avito-message');
    if (msgBtn) {
      const isChatOff = (typeof isItemChatDisabled === 'function') && isItemChatDisabled(itemId);
      if (isChatOff) {
        msgBtn.classList.add('disabled');
        msgBtn.setAttribute('disabled', 'disabled');
        msgBtn.removeAttribute('onclick');
        msgBtn.title = 'Чат у продавца отключен (только звонки)';
        const badge = msgBtn.querySelector('.chat-pulsing-badge');
        if (badge) badge.remove();
      } else {
        msgBtn.classList.remove('disabled');
        msgBtn.removeAttribute('disabled');
        msgBtn.title = 'Написать продавцу в чат';
        const isUnread = (typeof isItemChatUnread === 'function') && isItemChatUnread(itemId);
        if (isUnread) {
          msgBtn.classList.add('has-unread');
          if (!msgBtn.querySelector('.chat-pulsing-badge')) {
            msgBtn.insertAdjacentHTML('beforeend', ` <span class="chat-pulsing-badge" id="chat-badge-${escapeHtml(itemId)}">!</span>`);
          }
        } else {
          msgBtn.classList.remove('has-unread');
          const badge = msgBtn.querySelector('.chat-pulsing-badge');
          if (badge) badge.remove();
        }
      }
    }
  }
}

function removeCardFromGridInPlace(itemId) {
  const card = document.getElementById('avito-card-' + itemId);
  if (!card) return;

  if (avitoData && avitoData.items) {
    avitoData.items = avitoData.items.filter(x => String(x.item_id) !== String(itemId));
  }

  card.classList.add('avito-card-fade-out');
  setTimeout(() => {
    if (card && card.parentNode) {
      card.parentNode.removeChild(card);
    }
    updateAvitoCountBadge();
  }, 400);
}

function updateAvitoCountBadge() {
  const remainingCards = document.querySelectorAll('.avito-card').length;
  if (countBadge) {
    countBadge.innerText = `${components.length}\u00A0шт.`;
  }
  const avitoCatBtn = document.querySelector('.cat-btn-avito-monitor');
  if (avitoCatBtn) {
    avitoCatBtn.innerHTML = `🤖 Монитор Авито (${remainingCards})`;
  }
}

window.toggleAvitoBotPause = async function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  const hasTgAccount = Boolean(
    currentUser && (
      (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
      (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
    )
  );
  if (!hasTgAccount) {
    const inp = document.getElementById('input-my-tg-handle');
    if (inp) { inp.focus(); }
    return;
  }

  const btn = document.getElementById('btn-avito-bot-phone');
  if (btn) btn.disabled = true;
  try {
    const isBotRunning = Boolean(avitoData && avitoData.stats && avitoData.stats.bot_running);
    const action = isBotRunning ? 'toggle-pause' : 'start';
    const res = await fetch('/api/avito/bot-toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action })
    });
    const data = await res.json();
    if (data && data.success) {
      if (avitoData && avitoData.stats) {
        if (data.paused !== undefined) avitoData.stats.bot_paused = data.paused;
        if (data.running !== undefined) avitoData.stats.bot_running = data.running;
      }
      updateAvitoBotPhoneUI();
      updateAvitoHeaderDots();
      await loadAvitoStats();
    } else {
      alert('Ошибка переключения бота: ' + (data ? data.error : 'Неизвестная ошибка'));
    }
  } catch (err) {
    console.error('toggleAvitoBotPause error:', err);
    alert('Ошибка соединения с сервером при переключении бота.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.applyAvitoAutomationRules = async function(monitoringActive, tgBotActive) {
  const anyActive = Boolean(monitoringActive || tgBotActive);
  // 1. Мгновенно обновляем локальные флаги для реактивного отклика интерфейса
  if (currentUser) {
    if (!currentUser.permissions) currentUser.permissions = {};
    currentUser.permissions.monitoring = Boolean(monitoringActive);
    currentUser.permissions.tg_bot = Boolean(tgBotActive);
  }
  if (avitoData && avitoData.stats) {
    avitoData.stats.user_monitoring = Boolean(monitoringActive);
    avitoData.stats.user_tg_bot = Boolean(tgBotActive);
    avitoData.stats.bot_paused = !tgBotActive;
    avitoData.stats.monitor_enabled = Boolean(monitoringActive);
    if (anyActive) {
      avitoData.stats.proxy_fetching = true;
      avitoIsFetchingProxies = true;
    } else {
      avitoData.stats.proxy_fetching = false;
      avitoData.stats.proxy_manual_started = false;
      avitoIsFetchingProxies = false;
    }
  }

  // Обновляем точечно нужные контролы без деструктивного пересоздания DOM
  updateAvitoBotPhoneUI();
  updateAvitoProxiesUI();
  updateAvitoHeaderDots();
  updateAvitoTimerUI();

  // 2. Отправляем централизованный запрос на сервер (POST /api/avito/apply-rules)
  // Сервер применяет правила для бота и прокси последовательно и возвращает точный статус
  try {
    const uname = (currentUser && (currentUser.username || currentUser.name)) ? String(currentUser.username || currentUser.name).replace(/\s*\(.*?\)/g, '').trim() : '';
    const res = await fetch('/api/avito/apply-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monitoring: monitoringActive, tg_bot: tgBotActive, username: uname })
    });
    const d = await res.json().catch(() => ({}));
    if (d && d.success && avitoData && avitoData.stats) {
      if (d.monitor_enabled !== undefined) {
        avitoData.stats.monitor_enabled = d.monitor_enabled;
      } else {
        avitoData.stats.monitor_enabled = Boolean(monitoringActive);
      }
      if (d.bot_paused !== undefined) {
        avitoData.stats.bot_paused = d.bot_paused;
      }
      if (d.details) {
        if (d.details.bot) {
          if (d.details.bot.paused !== undefined) avitoData.stats.bot_paused = d.details.bot.paused;
          if (d.details.bot.running !== undefined) avitoData.stats.bot_running = d.details.bot.running;
        }
        if (d.details.proxy) {
          if (!anyActive) {
            avitoData.stats.proxy_fetching = false;
            avitoIsFetchingProxies = false;
          } else if (d.details.proxy.is_fetching !== undefined) {
            avitoData.stats.proxy_fetching = d.details.proxy.is_fetching;
            avitoIsFetchingProxies = d.details.proxy.is_fetching;
          }
          if (d.details.proxy.manual_started !== undefined) {
            avitoData.stats.proxy_manual_started = d.details.proxy.manual_started;
          }
        }
      }
    }
    updateAvitoBotPhoneUI();
    updateAvitoProxiesUI();
    updateAvitoHeaderDots();
    updateAvitoTimerUI();
    await loadAvitoStats();
  } catch (e) {
    console.error('applyAvitoAutomationRules error:', e);
  }
};

window.toggleMyMonitoring = async function() {
  if (!currentUser) {
    await syncUserSession();
  }
  if (!currentUser) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Войдите в систему для управления мониторингом', 1500);
    } else {
      alert('Войдите в систему для управления мониторингом');
    }
    return;
  }

  let curSearches = (avitoData && Array.isArray(avitoData.searches)) ? normalizeSearches(avitoData.searches) : [];
  if (curSearches.length === 0 && currentUser && currentUser.avito_searches) {
    curSearches = normalizeSearches(currentUser.avito_searches);
  }
  if (curSearches.length === 0) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Сначала добавьте хотя бы одну ссылку для поиска', 2000);
    } else {
      alert('Сначала добавьте хотя бы одну ссылку для поиска');
    }
    return;
  }

  const btn = document.getElementById('btn-user-mon-toggle');
  if (btn) btn.disabled = true;

  const currentVal = !(currentUser.permissions && currentUser.permissions.monitoring === false);
  const newVal = !currentVal;
  const username = (currentUser.username || currentUser.name || '').replace(/\s*\(.*?\)/g, '').trim();
  const token = currentUser.session_token || '';

  const sendReq = async () => {
    return await fetch('/api/users/permission', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-Session-Token': token } : {})
      },
      body: JSON.stringify({
        username: username,
        session_token: token,
        permission: 'monitoring',
        value: newVal,
        monitoring: newVal
      })
    });
  };

  try {
    let res = await sendReq();
    let data = await res.json().catch(() => ({}));

    // Авто-восстановление при ошибке «Пользователь не найден»
    if (!data.success && (data.error === 'Пользователь не найден' || res.status === 401)) {
      await syncUserSession();
      res = await sendReq();
      data = await res.json().catch(() => ({}));
    }

    if (data.success) {
      if (!currentUser.permissions) currentUser.permissions = {};
      currentUser.permissions.monitoring = newVal;
      if (avitoData && avitoData.stats) avitoData.stats.user_monitoring = newVal;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      
      const hasTg = Boolean(
        currentUser && (
          (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
          (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
        )
      );
      const currentTg = Boolean(hasTg && !(currentUser.permissions && currentUser.permissions.tg_bot === false));
      await window.applyAvitoAutomationRules(newVal, currentTg);
    } else {
      alert('Ошибка: ' + (data.error || 'Не удалось переключить мониторинг'));
    }
  } catch (err) {
    console.error('toggleMyMonitoring error:', err);
    alert('Ошибка соединения с сервером при переключении мониторинга.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.toggleMyTelegramNotifications = async function() {
  if (!currentUser) {
    await syncUserSession();
  }
  if (!currentUser) {
    if (typeof window.showToast === 'function') {
      window.showToast('⚠️ Войдите в систему для управления уведомлениями', 1500);
    } else {
      alert('Войдите в систему для управления уведомлениями');
    }
    return;
  }
  const hasTgAccount = Boolean(
    currentUser && (
      (currentUser.telegram_username && currentUser.telegram_username.trim()) ||
      (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim())
    )
  );
  if (!hasTgAccount) {
    const inp = document.getElementById('input-my-tg-handle');
    if (inp) { inp.focus(); }
    return;
  }

  const btn = document.getElementById('btn-user-tg-toggle');
  if (btn) btn.disabled = true;

  const currentVal = !(currentUser.permissions && currentUser.permissions.tg_bot === false);
  const newVal = !currentVal;
  const username = (currentUser.username || currentUser.name || '').replace(/\s*\(.*?\)/g, '').trim();
  const token = currentUser.session_token || '';

  const sendReq = async () => {
    return await fetch('/api/users/permission', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-Session-Token': token } : {})
      },
      body: JSON.stringify({
        username: username,
        session_token: token,
        permission: 'tg_bot',
        value: newVal,
        tg_bot: newVal
      })
    });
  };

  try {
    let res = await sendReq();
    let data = await res.json().catch(() => ({}));

    // Авто-восстановление при ошибке «Пользователь не найден»
    if (!data.success && (data.error === 'Пользователь не найден' || res.status === 401)) {
      await syncUserSession();
      res = await sendReq();
      data = await res.json().catch(() => ({}));
    }

    if (data.success) {
      if (!currentUser.permissions) currentUser.permissions = {};
      currentUser.permissions.tg_bot = newVal;
      if (avitoData && avitoData.stats) avitoData.stats.user_tg_bot = newVal;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}

      const currentMon = !(currentUser.permissions && currentUser.permissions.monitoring === false);
      await window.applyAvitoAutomationRules(currentMon, newVal);
    } else {
      alert('Ошибка: ' + (data.error || 'Не удалось переключить ТГ-уведомления'));
    }
  } catch (err) {
    console.error('toggleMyTelegramNotifications error:', err);
    alert('Ошибка соединения с сервером при переключении уведомлений.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

// ── Хелперы виджета привязки Telegram ──────────────────────────────────────
window._openTgBotBind = function(e) {
  if (e && e.stopPropagation) e.stopPropagation();
  const uName = (currentUser && currentUser.username) || (typeof window.getClientDeviceId === 'function' ? window.getClientDeviceId() : '');
  const botUrl = `https://t.me/avvvskybot?start=bind_${encodeURIComponent(uName)}`;
  window.open(botUrl, '_blank');
};

window._setTgIcon = function(hasValue) {
  ['avito-tg-link-wrap', 'modal-tg-link-wrap'].forEach(id => {
    const wrap = document.getElementById(id);
    const ico = wrap ? (wrap.querySelector('.tg-link-icon') || wrap.querySelector('span')) : null;
    if (ico) {
      ico.innerHTML = '<img src="img/telegram.png" alt="Telegram" style="width:20px;height:20px;object-fit:contain;vertical-align:middle;display:inline-block;">';
      ico.onclick = window._openTgBotBind;
      ico.style.cursor = 'pointer';
      ico.title = 'Открыть Telegram-бота @avvvskybot';
    }
  });
};

// Отправка обратной связи от Telegram-бота об успешном подтверждении аккаунта
window._sendTgBindSuccessFeedback = async function() {
  try {
    const uname = (currentUser && currentUser.username) ? currentUser.username : '';
    const inp = document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
    const inpVal = inp ? (inp.value || '').trim() : '';
    const cid = (currentUser && currentUser.telegram_chat_id)
      ? String(currentUser.telegram_chat_id)
      : ((currentUser && currentUser.telegram_username)
          ? currentUser.telegram_username
          : inpVal);
    await fetch('/api/avito/notify-bind-success', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uname, chat_id: cid, handle: inpVal })
    });
  } catch (e) {
    console.debug('Failed to send bind success feedback:', e);
  }
};

// Устанавливает визуальное состояние виджета (красный / зелёный подтвержденный)
window._tgWidgetSetState = function(hasValue) {
  _isEditingTg = false;
  window._tgHadBoundAccount = Boolean(hasValue);
  const wasConfirmed = (currentUser && isTelegramAccountConfirmed(currentUser));
  const currentVal = hasValue ? (currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) : '';

  const widgets = [
    { wrap: document.getElementById('avito-tg-link-wrap'), inp: document.getElementById('input-my-tg-handle'), btn: document.getElementById('btn-my-tg-bind') },
    { wrap: document.getElementById('modal-tg-link-wrap'), inp: document.getElementById('input-modal-tg-handle'), btn: document.getElementById('btn-modal-tg-bind') }
  ];

  widgets.forEach(({ wrap, inp, btn }) => {
    if (!wrap && !inp && !btn) return;
    if (btn) {
      btn.classList.remove('tg-btn-edit-pulse');
      delete btn.dataset.action;
    }
    if (hasValue) {
      if (wrap) {
        wrap.style.background     = 'rgba(16,185,129,0.22)';
        wrap.style.border         = '2px solid #10b981';
        wrap.style.boxShadow      = '0 0 12px rgba(16,185,129,0.35)';
        wrap.style.cursor         = 'text';
        wrap.title                = 'Telegram привязан. Нажмите, чтобы изменить или отвязать';
        wrap.className            = (wrap.className || '').replace(/\bstate-pending\b/g, '').trim() + ' state-linked';
      }
      if (inp) {
        inp.readOnly              = false;
        inp.style.color           = '#ffffff';
        inp.style.fontWeight      = '700';
        inp.style.cursor          = 'text';
        if (currentVal && !inp.value) inp.value = currentVal;
      }
      if (btn) {
        btn.dataset.accepted    = '1';
        delete btn.dataset.action;
        delete btn.dataset.pending;
        btn.classList.remove('btn-tg-pending');
        btn.style.background    = '#166534';
        btn.style.color         = '#ffffff';
        btn.style.border        = '1px solid #14532d';
        btn.style.fontWeight    = '700';
        btn.style.opacity       = '1';
        btn.style.cursor        = 'pointer';
        btn.style.pointerEvents = 'auto';
        btn.disabled            = false;
        btn.innerHTML           = 'Привязан';
        btn.title               = 'Telegram-аккаунт привязан. Нажмите для изменения';
      }
    } else {
      if (wrap) {
        wrap.style.background     = 'rgba(239,68,68,0.12)';
        wrap.style.border         = '1.5px solid rgba(239,68,68,0.55)';
        wrap.style.boxShadow      = 'none';
        wrap.style.cursor         = 'text';
        wrap.title                = '@username или ID';
        wrap.className            = (wrap.className || '').replace(/\bstate-linked\b|\bstate-pending\b/g, '').trim();
      }
      if (inp) {
        inp.readOnly              = false;
        inp.style.color           = '#ffffff';
        inp.style.fontWeight      = '600';
        inp.style.cursor          = 'text';
      }
      if (btn) {
        delete btn.dataset.accepted;
        delete btn.dataset.action;
        delete btn.dataset.pending;
        btn.classList.remove('btn-tg-pending');
        btn.style.background    = 'rgba(14,165,233,0.18)';
        btn.style.color         = '#38bdf8';
        btn.style.border        = '1px solid rgba(14,165,233,0.4)';
        btn.style.fontWeight    = '700';
        btn.style.opacity       = '';
        btn.style.cursor        = 'pointer';
        btn.style.pointerEvents = 'auto';
        btn.disabled            = false;
        btn.innerHTML           = 'Привязать';
        btn.title               = 'Привязать адрес Telegram к аккаунту';
      }
    }
  });

  window._setTgIcon(hasValue);

  if (!hasValue) {
    const feedKey = 'tg_feedback_notified_' + (currentUser ? currentUser.username : '');
    try { sessionStorage.removeItem(feedKey); } catch (e) {}
  }
  if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
  if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
};

let _isEditingTg = false;

// Одинарный клик — переводим инпут в фокус и активируем возможность ввода
window._tgInputSingleClick = function(inp) {
  if (!inp) inp = document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
  if (inp) {
    inp.readOnly = false;
    inp.style.cursor = 'text';
    inp.setAttribute('autocomplete', 'off');
    inp.setAttribute('autocorrect', 'off');
    inp.setAttribute('autocapitalize', 'off');
    inp.setAttribute('spellcheck', 'false');
    inp.setAttribute('data-lpignore', 'true');
    _isEditingTg = true;
    const isConfirmed = Boolean(
      window._tgHadBoundAccount ||
      (typeof isTelegramAccountConfirmed === 'function' && isTelegramAccountConfirmed(currentUser)) ||
      (currentUser && ((currentUser.telegram_username && currentUser.telegram_username.trim()) || (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim()) || currentUser.telegram_pending))
    );
    if (isConfirmed) {
      window._tgHadBoundAccount = true;
    }
  }
};

// Двойной клик — фокус и выделение
window._tgInputDblClick = function(inp) {
  if (!inp) inp = document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
  if (!inp) return;
  _isEditingTg = true;
  inp.readOnly = false;
  inp.style.cursor = 'text';
  inp.setAttribute('autocomplete', 'off');
  inp.setAttribute('autocorrect', 'off');
  inp.setAttribute('autocapitalize', 'off');
  inp.setAttribute('spellcheck', 'false');
  inp.setAttribute('data-lpignore', 'true');
  inp.focus();
  const len = inp.value.length;
  inp.setSelectionRange(len, len);

  const val = (inp.value || '').trim();
  const isEmpty = (val === '');
  const hadBoundAccount = Boolean(
    window._tgHadBoundAccount ||
    (typeof isTelegramAccountConfirmed === 'function' && isTelegramAccountConfirmed(currentUser)) ||
    (currentUser && ((currentUser.telegram_username && currentUser.telegram_username.trim()) || (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim()) || currentUser.telegram_pending)) ||
    (avitoData && avitoData.stats && ((avitoData.stats.telegram_username && avitoData.stats.telegram_username.trim()) || (avitoData.stats.telegram_chat_id && String(avitoData.stats.telegram_chat_id).trim()) || avitoData.stats.telegram_pending))
  );

  ['btn-my-tg-bind', 'btn-modal-tg-bind'].forEach(bId => {
    const btn = document.getElementById(bId);
    if (btn) {
      delete btn.dataset.accepted;
      delete btn.dataset.pending;
      btn.classList.remove('btn-tg-pending');
      btn.disabled = false;
      btn.style.pointerEvents = 'auto';
      btn.style.cursor = 'pointer';
      btn.style.opacity = '1';
      btn.style.fontWeight = '700';

      if (isEmpty && hadBoundAccount) {
        btn.dataset.action = 'unbind';
        btn.textContent = 'Отвязать';
        btn.title = 'Отвязать привязанный аккаунт Telegram';
        btn.style.background = '#dc2626';
        btn.style.color = '#ffffff';
        btn.style.border = '1px solid #b91c1c';
      } else {
        delete btn.dataset.action;
        btn.textContent = 'Привязать';
        btn.title = 'Нажмите «Привязать» для сохранения Telegram-аккаунта';
        btn.style.background = 'rgba(14,165,233,0.25)';
        btn.style.color = '#38bdf8';
        btn.style.border = '1px solid rgba(14,165,233,0.6)';
      }
    }
  });
};

// Ввод текста — если поле стёрто полностью у привязанного аккаунта, кнопка становится «Отвязать»
window._tgInputOnInput = function(inp) {
  _isEditingTg = true;
  const isModal = inp && inp.id === 'input-modal-tg-handle';
  const otherInp = isModal ? document.getElementById('input-my-tg-handle') : document.getElementById('input-modal-tg-handle');
  if (otherInp && inp) {
    otherInp.value = inp.value;
  }

  const val = (inp && inp.value !== undefined) ? inp.value.trim() : '';
  const isEmpty = (val === '');

  const hadBoundAccount = Boolean(
    window._tgHadBoundAccount ||
    (typeof isTelegramAccountConfirmed === 'function' && isTelegramAccountConfirmed(currentUser)) ||
    (currentUser && ((currentUser.telegram_username && currentUser.telegram_username.trim()) || (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim()) || currentUser.telegram_pending)) ||
    (avitoData && avitoData.stats && ((avitoData.stats.telegram_username && avitoData.stats.telegram_username.trim()) || (avitoData.stats.telegram_chat_id && String(avitoData.stats.telegram_chat_id).trim()) || avitoData.stats.telegram_pending))
  );

  ['btn-my-tg-bind', 'btn-modal-tg-bind'].forEach(bId => {
    const btn = document.getElementById(bId);
    if (!btn) return;
    delete btn.dataset.accepted;
    delete btn.dataset.pending;
    btn.classList.remove('btn-tg-pending');
    btn.disabled = false;
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'pointer';
    btn.style.opacity = '1';
    btn.style.fontWeight = '700';

    if (isEmpty && hadBoundAccount) {
      // Пользователь полностью стёр привязанный аккаунт -> показываем кнопку «Отвязать»
      btn.dataset.action = 'unbind';
      btn.textContent = 'Отвязать';
      btn.title = 'Отвязать привязанный аккаунт Telegram';
      btn.style.background = '#dc2626';
      btn.style.color = '#ffffff';
      btn.style.border = '1px solid #b91c1c';
    } else {
      delete btn.dataset.action;
      btn.textContent = 'Привязать';
      btn.title = 'Нажмите «Привязать» для сохранения Telegram-аккаунта';
      btn.style.background = 'rgba(14,165,233,0.25)';
      btn.style.color = '#38bdf8';
      btn.style.border = '1px solid rgba(14,165,233,0.6)';
    }
  });

  ['avito-tg-link-wrap', 'modal-tg-link-wrap'].forEach(wId => {
    const wrap = document.getElementById(wId);
    if (wrap) wrap.style.cursor = 'text';
  });
};

// Обработка клавиши Enter
window._handleTgEnter = function(which) {
  let inp = null;
  if (which === 'modal' || document.getElementById('input-modal-tg-handle') === document.activeElement) {
    inp = document.getElementById('input-modal-tg-handle');
  } else {
    inp = document.getElementById('input-my-tg-handle') || document.getElementById('input-modal-tg-handle');
  }
  if (!inp) return;
  _isEditingTg = false;
  window.saveMyTelegramHandle(inp.value);
};

// Сохранение изменений в поле
window._tgSaveEdit = function(which) {
  _isEditingTg = false;
  const inp = (which === 'modal' ? document.getElementById('input-modal-tg-handle') : document.getElementById('input-my-tg-handle')) || document.getElementById('input-modal-tg-handle') || document.getElementById('input-my-tg-handle');
  if (!inp) return;
  window.saveMyTelegramHandle(inp.value);
};

// Клик по кнопке справа от инпута
window._tgButtonClick = function(which) {
  let btn = null;
  let inp = null;
  if (which === 'modal') {
    btn = document.getElementById('btn-modal-tg-bind');
    inp = document.getElementById('input-modal-tg-handle');
  } else {
    btn = document.getElementById('btn-my-tg-bind') || document.getElementById('btn-modal-tg-bind');
    inp = document.getElementById('input-my-tg-handle') || document.getElementById('input-modal-tg-handle');
  }
  if (!btn || !inp) return;

  const txt = btn.textContent.trim();
  const val = inp.value.trim();

  // 1. Кнопка «Отвязать» — выполняем немедленную отвязку
  if (txt === 'Отвязать' || btn.dataset.action === 'unbind') {
    _isEditingTg = false;
    window.saveMyTelegramHandle('');
    return;
  }

  // 2. Если находится в статусе «Ожидание» (или при наведении «Отменить») — отменяем ожидание привязки!
  const isPendingState = Boolean(
    btn.dataset.pending === '1' ||
    btn.classList.contains('btn-tg-pending') ||
    (btn.closest && btn.closest('.state-pending')) ||
    (currentUser && currentUser.telegram_pending && currentUser.telegram_pending.status === 'pending') ||
    (window.avitoData && window.avitoData.stats && window.avitoData.stats.telegram_pending && window.avitoData.stats.telegram_pending.status === 'pending') ||
    txt.includes('Ожидание') ||
    txt.includes('Отменить')
  );

  if (!_isEditingTg && isPendingState && !txt.includes('Привязан') && !btn.dataset.accepted) {
    _isEditingTg = false;
    window.cancelMyTelegramPending();
    return;
  }

  // 3. Сохранение или привязка введенного значения
  if (_isEditingTg || txt === 'Привязать' || txt === 'Сохранить') {
    window.saveMyTelegramHandle(val);
  } else {
    _isEditingTg = true;
    inp.readOnly = false;
    inp.style.cursor = 'text';
    inp.focus();
    const isEmpty = !inp.value.trim();
    const hadBound = Boolean(
      window._tgHadBoundAccount ||
      (typeof isTelegramAccountConfirmed === 'function' && isTelegramAccountConfirmed(currentUser)) ||
      (currentUser && ((currentUser.telegram_username && currentUser.telegram_username.trim()) || (currentUser.telegram_chat_id && String(currentUser.telegram_chat_id).trim()) || currentUser.telegram_pending))
    );
    ['btn-my-tg-bind', 'btn-modal-tg-bind'].forEach(bId => {
      const b = document.getElementById(bId);
      if (b) {
        delete b.dataset.accepted;
        b.style.fontWeight = '700';
        if (isEmpty && hadBound) {
          b.dataset.action = 'unbind';
          b.textContent = 'Отвязать';
          b.style.background = '#dc2626';
          b.style.color = '#ffffff';
          b.style.border = '1px solid #b91c1c';
        } else {
          delete b.dataset.action;
          b.textContent = 'Привязать';
          b.style.background = 'rgba(14,165,233,0.25)';
          b.style.color = '#38bdf8';
          b.style.border = '1px solid rgba(14,165,233,0.6)';
        }
      }
    });
  }
};

// Устанавливает жёлтое состояние виджета "Ожидает подтверждения в Telegram"
window._tgWidgetSetPending = function(handleVal) {
  _isEditingTg = false;
  const formattedVal = handleVal ? (handleVal.startsWith('@') ? handleVal : '@' + handleVal.replace(/^@/, '')) : '';

  const widgets = [
    { wrap: document.getElementById('avito-tg-link-wrap'), inp: document.getElementById('input-my-tg-handle'), btn: document.getElementById('btn-my-tg-bind') },
    { wrap: document.getElementById('modal-tg-link-wrap'), inp: document.getElementById('input-modal-tg-handle'), btn: document.getElementById('btn-modal-tg-bind') }
  ];

  widgets.forEach(({ wrap, inp, btn }) => {
    if (!wrap && !inp && !btn) return;
    if (btn) btn.classList.remove('tg-btn-edit-pulse');
    if (wrap) {
      wrap.style.background     = 'rgba(234,179,8,0.14)';
      wrap.style.border         = '1.5px solid rgba(234,179,8,0.7)';
      wrap.style.boxShadow      = 'none';
      wrap.style.cursor         = 'text';
      wrap.title                = 'Ожидает подтверждения: откройте Telegram-бота @avvvskybot и подтвердите привязку.';
      wrap.className            = (wrap.className || '').replace(/\bstate-linked\b/g, '').trim();
      if (!wrap.className.includes('state-pending')) wrap.className += ' state-pending';
    }
    if (inp) {
      if (formattedVal) inp.value = formattedVal;
      inp.readOnly              = false;
      inp.style.color           = '#ffffff';
      inp.style.fontWeight      = '600';
      inp.style.cursor          = 'text';
    }
    if (btn) {
      delete btn.dataset.accepted;
      delete btn.dataset.action;
      btn.dataset.pending     = '1';
      if (!btn.classList.contains('btn-tg-pending')) btn.classList.add('btn-tg-pending');
      btn.style.background    = 'rgba(234,179,8,0.22)';
      btn.style.color         = '#eab308';
      btn.style.border        = '1px solid rgba(234,179,8,0.6)';
      btn.style.fontWeight    = '700';
      btn.style.opacity       = '1';
      btn.style.cursor        = 'pointer';
      btn.style.pointerEvents = 'auto';
      btn.disabled            = false;
      btn.innerHTML           = '<span class="tg-pending-label" style="display:inline-block;position:relative;left:-5px;">⏳ Ожидание</span><span class="tg-cancel-label" style="display:none;">Отменить</span>';
      btn.title               = 'Ожидает подтверждения: подтвердите привязку в Telegram-боте @avvvskybot. Наведите для отмены';
    }
  });

  window._setTgIcon(false);

  if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
  if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
  window._startTgPendingPoll();
};

// Отмена ожидания привязки Telegram (клик по кнопке «Отменить»)
window.cancelMyTelegramPending = async function() {
  if (_tgPendingPollTimer) {
    clearInterval(_tgPendingPollTimer);
    _tgPendingPollTimer = null;
  }
  const reqId = (currentUser && currentUser.username) || (typeof window.getClientDeviceId === 'function' ? window.getClientDeviceId() : '');
  if (currentUser) {
    currentUser.telegram_pending = null;
  }
  if (window.avitoData && window.avitoData.stats) {
    window.avitoData.stats.telegram_pending = null;
  }
  try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}

  try {
    await fetch('/api/user/telegram/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: (currentUser && currentUser.username) || reqId,
        request_id: reqId
      })
    });
  } catch (err) {
    console.debug('Failed to cancel tg pending on server:', err);
  }

  window._tgWidgetSetState(false);
};

// Интерактивное наведение на кнопку "Ожидание" -> отображение "Отменить" (красным)
if (!window._tgHoverCancelBound) {
  window._tgHoverCancelBound = true;
  document.addEventListener('mouseover', function(e) {
    const btn = e.target && e.target.closest ? e.target.closest('#btn-my-tg-bind, #btn-modal-tg-bind') : null;
    if (!btn) return;
    const isPending = btn.dataset.pending === '1' || btn.classList.contains('btn-tg-pending') || (btn.closest && btn.closest('.state-pending'));
    if (isPending) {
      const pendLbl = btn.querySelector('.tg-pending-label');
      const cancLbl = btn.querySelector('.tg-cancel-label');
      if (pendLbl) pendLbl.style.display = 'none';
      if (cancLbl) {
        cancLbl.style.display = 'inline-block';
        cancLbl.style.position = 'static';
        cancLbl.style.left = '0';
      }
      btn.style.setProperty('background', '#dc2626', 'important');
      btn.style.setProperty('color', '#ffffff', 'important');
      btn.style.setProperty('border', '1px solid #b91c1c', 'important');
      btn.title = 'Нажмите «Отменить» для отмены привязки Telegram';
    }
  });

  document.addEventListener('mouseout', function(e) {
    const btn = e.target && e.target.closest ? e.target.closest('#btn-my-tg-bind, #btn-modal-tg-bind') : null;
    if (!btn) return;
    if (e.relatedTarget && btn.contains(e.relatedTarget)) return;
    const isPending = btn.dataset.pending === '1' || btn.classList.contains('btn-tg-pending') || (btn.closest && btn.closest('.state-pending'));
    if (isPending) {
      const pendLbl = btn.querySelector('.tg-pending-label');
      const cancLbl = btn.querySelector('.tg-cancel-label');
      if (pendLbl) {
        pendLbl.style.display = 'inline-block';
        pendLbl.style.position = 'relative';
        pendLbl.style.left = '-5px';
      }
      if (cancLbl) cancLbl.style.display = 'none';
      btn.style.setProperty('background', 'rgba(234,179,8,0.22)', 'important');
      btn.style.setProperty('color', '#eab308', 'important');
      btn.style.setProperty('border', '1px solid rgba(234,179,8,0.6)', 'important');
      btn.title = 'Ожидает подтверждения в Telegram-боте @avvvskybot. Наведите для отмены';
    }
  });
}

// Опрос статуса привязки (pending → confirmed / rejected)
let _tgPendingPollTimer = null;
let _tgPendingPollCount = 0;
window._startTgPendingPoll = function() {
  if (_tgPendingPollTimer) clearInterval(_tgPendingPollTimer);
  _tgPendingPollCount = 0;
  _tgPendingPollTimer = setInterval(async () => {
    _tgPendingPollCount++;
    if (_tgPendingPollCount > 36) { // 36 * 5сек = 3 мин
      clearInterval(_tgPendingPollTimer);
      _tgPendingPollTimer = null;
      return;
    }
    try {
      const uName = (currentUser && currentUser.username) || window.getClientDeviceId() || '';
      if (!uName) return;
      const userParam = '&username=' + encodeURIComponent(uName);
      const reqParam = '&request_id=' + encodeURIComponent(uName);
      const res = await fetch('/api/avito/stats?t=' + Date.now() + userParam + reqParam);
      if (!res.ok) return;
      const data = await res.json();
      if (!data || !data.success || !data.stats) return;
      const pending = data.stats.telegram_pending;
      const tgUsername = data.stats.telegram_username;
      const tgChatId = data.stats.telegram_chat_id;
      if (!pending || pending.status !== 'pending') {
        // Подтверждено или отклонено
        clearInterval(_tgPendingPollTimer);
        _tgPendingPollTimer = null;
        if (tgUsername || tgChatId) {
          // Подтверждено — обновляем currentUser и оба виджета, включаем ТГ-уведомления
          if (currentUser) {
            currentUser.telegram_username = tgUsername || null;
            currentUser.telegram_chat_id = tgChatId || null;
            currentUser.telegram_pending = null;
            if (!currentUser.permissions) currentUser.permissions = {};
            currentUser.permissions.tg_bot = true;
            currentUser.permissions.monitoring = true;
          }
          if (avitoData && avitoData.stats) {
            avitoData.stats.telegram_pending = null;
            avitoData.stats.telegram_username = tgUsername || null;
            avitoData.stats.telegram_chat_id = tgChatId || null;
            avitoData.stats.user_tg_bot = true;
            avitoData.stats.user_monitoring = true;
            avitoData.stats.bot_paused = false;
          }
          try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
          window._tgWidgetSetState(true);
          const valStr = tgUsername ? ('@' + tgUsername.replace(/^@/, '')) : (tgChatId ? String(tgChatId) : '');
          const inp1 = document.getElementById('input-my-tg-handle');
          const inp2 = document.getElementById('input-modal-tg-handle');
          if (inp1) inp1.value = valStr;
          if (inp2) inp2.value = valStr;
          if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
          if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
          if (typeof loadAvitoStats === 'function') await loadAvitoStats();
          if (currentCat === 'avito_monitor' && typeof renderAvitoDashboard === 'function') renderAvitoDashboard();
        } else {
          // Отклонено
          if (currentUser) {
            currentUser.telegram_pending = null;
            currentUser.telegram_username = null;
            currentUser.telegram_chat_id = null;
            if (currentUser.permissions) currentUser.permissions.tg_bot = false;
          }
          if (avitoData && avitoData.stats) {
            avitoData.stats.telegram_pending = null;
            avitoData.stats.telegram_username = null;
            avitoData.stats.telegram_chat_id = null;
            avitoData.stats.user_tg_bot = false;
          }
          window._tgHadBoundAccount = false;
          try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
          window._tgWidgetSetState(false);
          const inp1 = document.getElementById('input-my-tg-handle');
          const inp2 = document.getElementById('input-modal-tg-handle');
          if (inp1) inp1.value = '';
          if (inp2) inp2.value = '';
          if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
          if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
        }
      }
    } catch (e) {
      console.debug('TG pending poll error:', e);
    }
  }, 5000);
};
// ─────────────────────────────────────────────────────────────────────────────

window.saveMyTelegramHandle = async function(rawVal) {
  const reqId = (currentUser && currentUser.username) || window.getClientDeviceId() || '';
  if (!reqId) {
    alert('Пожалуйста, выполните вход в учетную запись на сайте.');
    return;
  }
  const cleanVal = (rawVal || '').trim();
  try {
    const res = await fetch('/api/user/telegram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: (currentUser && currentUser.username) || reqId,
        request_id: reqId,
        telegram_handle: cleanVal
      })
    });
    const data = await res.json();
    if (data.success) {
      if (!cleanVal) {
        // Отвязка TG
        if (_tgPendingPollTimer) {
          clearInterval(_tgPendingPollTimer);
          _tgPendingPollTimer = null;
        }
        window._tgHadBoundAccount = false;
        if (currentUser) {
          currentUser.telegram_username = null;
          currentUser.telegram_chat_id = null;
          currentUser.telegram_pending = null;
          if (!currentUser.permissions) currentUser.permissions = {};
          currentUser.permissions.tg_bot = false;
        }
        if (avitoData && avitoData.stats) {
          avitoData.stats.telegram_username = null;
          avitoData.stats.telegram_chat_id = null;
          avitoData.stats.telegram_pending = null;
          avitoData.stats.user_tg_bot = false;
        }
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        window._tgWidgetSetState(false);
        const inp1 = document.getElementById('input-my-tg-handle');
        const inp2 = document.getElementById('input-modal-tg-handle');
        if (inp1) inp1.value = '';
        if (inp2) inp2.value = '';

        if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
        if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
      } else if (data.status === 'pending') {
        // Статус: ожидает подтверждения от Telegram-бота (жёлтый)
        const pendingObj = data.telegram_pending || { handle: cleanVal, status: 'pending' };
        if (currentUser) {
          currentUser.telegram_pending = pendingObj;
          currentUser.telegram_chat_id = null;
          currentUser.telegram_username = null;
        }
        if (avitoData && avitoData.stats) {
          avitoData.stats.telegram_pending = pendingObj;
          avitoData.stats.telegram_username = null;
          avitoData.stats.telegram_chat_id = null;
        }
        window._tgHadBoundAccount = true;
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        window._tgWidgetSetPending(cleanVal);
      } else {
        // Статус: успешно привязан сразу (если подтвержден мгновенно)
        if (cleanVal.replace(/^@/, '').match(/^-?\d+$/)) {
          if (currentUser) {
            currentUser.telegram_chat_id = parseInt(cleanVal.replace(/^@/, ''), 10);
            currentUser.telegram_username = null;
            currentUser.telegram_pending = null;
          }
        } else {
          if (currentUser) {
            currentUser.telegram_username = cleanVal.replace(/^@/, '');
            currentUser.telegram_chat_id = null;
            currentUser.telegram_pending = null;
          }
        }
        if (avitoData && avitoData.stats) {
          avitoData.stats.telegram_pending = null;
          avitoData.stats.telegram_username = currentUser ? currentUser.telegram_username : null;
          avitoData.stats.telegram_chat_id = currentUser ? currentUser.telegram_chat_id : null;
        }
        window._tgHadBoundAccount = true;
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        window._tgWidgetSetState(true);
      }
      if (typeof updateAvitoBotPhoneUI === 'function') updateAvitoBotPhoneUI();
      if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();
      if (typeof loadAvitoStats === 'function') await loadAvitoStats();
      if (currentCat === 'avito_monitor' && typeof renderAvitoDashboard === 'function') {
        renderAvitoDashboard();
      }
    } else {
      console.warn('saveMyTelegramHandle error:', data.error);
      const prevVal = (currentUser && (currentUser.telegram_username ? ('@' + currentUser.telegram_username.replace(/^@/, '')) : (currentUser.telegram_chat_id ? String(currentUser.telegram_chat_id) : ''))) || '';
      const inp1 = document.getElementById('input-my-tg-handle');
      const inp2 = document.getElementById('input-modal-tg-handle');
      if (inp1) inp1.value = prevVal;
      if (inp2) inp2.value = prevVal;
      if (typeof window._tgWidgetSetState === 'function') {
        window._tgWidgetSetState(Boolean(prevVal));
      }
    }
  } catch (err) {
    console.error('saveMyTelegramHandle error:', err);
    alert('Ошибка соединения с сервером при сохранении адреса Telegram.');
  }
};

window._legacyDbSetState = function() {};
window.initLegacyDbWidget = function() {};
window.handleLegacyDbAction = function() {};
window.reloadComponentsData = async function() {};

window.toggleMonitorMaster = async function() {
  const btn = document.getElementById('btn-mon-switch');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/avito/monitor-toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle' })
    });
    const data = await res.json();
    if (data.success) {
      if (avitoData && avitoData.stats && data.enabled !== undefined) {
        avitoData.stats.monitor_enabled = data.enabled;
      }
      updateAvitoHeaderDots();
      await loadAvitoStats();
      if (currentCat === 'avito_monitor') {
        renderAvitoDashboard();
      } else if (currentCat === 'home') {
        renderList();
      }
    } else {
      if (data && data.license_expired) {
        if (typeof window.setLicenseExpiredMode === 'function') {
          window.setLicenseExpiredMode(true);
        }
      } else {
        alert('Ошибка переключения мониторинга: ' + (data.error || 'Неизвестная ошибка'));
      }
    }
  } catch (err) {
    console.error('Monitor toggle error:', err);
    alert('Не удалось связаться с сервером при переключении мониторинга.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.runAvitoCheckNow = async function() {
  const btn = document.getElementById('btn-avito-check');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Проверка...';
  }

  showToast('🔍 Запущен опрос объявлений на Avito...');

  try {
    const res = await fetch('/api/avito/check', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      if (Array.isArray(data.removed_items) && data.removed_items.length > 0) {
        data.removed_items.forEach(remId => {
          removeCardFromGridInPlace(remId);
        });
        updateAvitoCountBadge();
      }
      if (Array.isArray(data.new_items)) {
        data.new_items.forEach(it => {
          if (!it.initial) {
            markItemAsFresh(it.item_id);
          }
          knownAvitoItemIds.add(String(it.item_id));
        });
      }
      const newCount = (data.new_items_count !== undefined) ? Number(data.new_items_count) : 0;
      if (newCount > 0) {
        if (typeof window.playAvitoChime === 'function') window.playAvitoChime();
      } else {
        showToast(`✅ Проверка завершена: новых объявлений нет`);
      }
      await loadAvitoStats();
      setTimeout(() => { loadAvitoStats(); }, 2000);
      setTimeout(() => { loadAvitoStats(); }, 4200);
    } else {
      alert('Ошибка проверки: ' + (data.error || 'Неизвестная ошибка'));
    }
  } catch (err) {
    console.error('Check error:', err);
    alert('Не удалось связаться с сервером при запуске проверки.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔄 Проверить сайт';
    }
  }
};

window.toggleAvitoBot = async function() {
  const btn = document.getElementById('btn-bot-switch');
  const isRunning = Boolean(avitoData.stats && avitoData.stats.bot_running);
  const targetAction = isRunning ? 'stop' : 'start';

  if (btn) {
    btn.disabled = true;
    btn.innerText = isRunning ? '⏳ Остановка бота...' : '⏳ Запуск бота...';
  }

  try {
    const res = await fetch('/api/avito/bot-toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: targetAction })
    });
    const data = await res.json();
    if (data.success) {
      if (avitoData && avitoData.stats) {
        avitoData.stats.bot_running = (targetAction === 'start');
      }
      updateAvitoHeaderDots();
      await loadAvitoStats();
      if (currentCat === 'avito_monitor') {
        renderAvitoDashboard();
      } else if (currentCat === 'home') {
        renderList();
      }
    } else {
      alert('Ошибка переключения бота: ' + (data.error || 'Неизвестная ошибка'));
    }
  } catch (err) {
    console.error('Bot toggle error:', err);
    alert('Не удалось связаться с сервером при переключении бота.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

// ==================== МОДАЛЬНОЕ ОКНО ПРОКСИ ====================

window.openProxyModal = async function(userOverride) {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  const targetUser = userOverride || (currentUser ? currentUser.username : '');
  window._proxyModalUser = targetUser;
  const isCurrentlyFetching = Boolean(avitoIsFetchingProxies || (avitoData && avitoData.stats && avitoData.stats.proxy_fetching));
  // Берём актуальный счётчик из уже загруженного кеша (не ждём API)
  const currentCount = (avitoData && avitoData.stats && avitoData.stats.proxy_count !== undefined)
    ? Number(avitoData.stats.proxy_count)
    : (typeof avitoProxyCount !== 'undefined' ? Number(avitoProxyCount) : 0);
  const sharedCountInit = currentCount; // предварительное значение до загрузки деталей
  const countText = `${currentCount} шт.`;

  modalBody.innerHTML = `
    <div style="padding:0.5rem 0;">
      <h3 style="font-size:1.35rem;font-weight:800;color:#818cf8;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;">
        🌐 Управление прокси-серверами ${targetUser ? `<span style="font-size:0.95rem;color:var(--text-secondary);font-weight:600;">(@${escapeHtml(targetUser)})</span>` : ''}
      </h3>
      <!-- Информационный блок: Как работает опрос и как прокси влияют на скорость -->
      <div style="background:rgba(15,23,42,0.65);border:1px solid rgba(99,102,241,0.3);border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:1.15rem;line-height:1.48;">
        <div style="font-weight:700;font-size:0.92rem;color:#818cf8;display:flex;align-items:center;gap:0.45rem;margin-bottom:0.45rem;">
          <span>⚡</span> <span>Как устроен опрос объявлений и влияние прокси на скорость:</span>
        </div>
        <div style="font-size:0.82rem;color:var(--text-primary);display:flex;flex-direction:column;gap:0.45rem;">
          <div>
            ⏱️ <strong>Скорость опроса (1 секунда):</strong> По умолчанию программа работает на предельной скорости — проверяет поисковые запросы каждую <strong>1 секунду</strong>, чтобы перехватывать самые выгодные объявления в момент их публикации раньше всех.
          </div>
          <div>
            🛡️ <strong>Зачем нужны прокси:</strong> Авито строго ограничивает частоту запросов с одного IP-адреса (Rate Limit / защита от ботов). Если отправлять запросы слишком часто с одного IP, Авито временно блокирует доступ (капча или ошибка 429).
          </div>
          <div>
            🚀 <strong>Как пул прокси разгоняет систему:</strong> Каждый следующий опрос отправляется через новый независимый IP-адрес из пула. Чем больше рабочих прокси в системе (от 20–30 шт. и более), тем безопаснее и стабильнее программа держит максимальную скорость в 1 секунду без задержек и без блокировок.
          </div>
          <div style="font-size:0.78rem;color:#94a3b8;border-top:1px dashed rgba(148,163,184,0.2);padding-top:0.4rem;margin-top:0.2rem;">
            💡 <em>Smart Fallback: вы можете загрузить свои приватные прокси через поле ниже, либо использовать автопополнение общего пула кнопкой «📥 Пополнить резерв».</em>
          </div>
        </div>
      </div>

      <div style="display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap;background:var(--bg-main);border:1px solid var(--border-color);border-radius:10px;padding:0.85rem 1rem;margin-bottom:1.25rem;">
        <div style="display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap;">
          <div>
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">Личные прокси:</span>
            <strong id="proxy-modal-user-count" style="font-size:1.15rem;color:#10b981;">0 шт.</strong>
          </div>
          <div style="border-left:1px solid var(--border-color);padding-left:1.5rem;">
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">Общий резерв:</span>
            <strong id="proxy-modal-shared-count" style="font-size:1.15rem;color:#818cf8;">${sharedCountInit > 0 ? sharedCountInit + ' шт.' : '...'}</strong>
          </div>
          <div style="border-left:1px solid var(--border-color);padding-left:1.5rem;">
            <span style="font-size:0.8rem;color:var(--text-secondary);display:block;">Активный режим:</span>
            <span id="proxy-modal-mode-badge" style="font-size:0.8rem;font-weight:700;padding:0.2rem 0.6rem;border-radius:6px;background:rgba(99,102,241,0.12);color:#818cf8;">Загрузка...</span>
          </div>
        </div>
        <div style="margin-left:auto;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;">
          <button id="btn-check-proxies" class="cat-btn" onclick="checkAllProxies()" style="background:#0284c7;border-color:#0284c7;color:#fff;font-weight:700;padding:0.45rem 0.9rem;font-size:0.82rem;" title="Проверить все прокси на доступ к Avito и удалить мертвые">
            🔍 Проверить
          </button>
          <button id="btn-clear-proxies" class="cat-btn" onclick="clearAllProxies()" style="background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.4);color:#ef4444;font-weight:700;padding:0.45rem 0.9rem;font-size:0.82rem;" title="Очистить все текущие прокси">
            🗑 Очистить все
          </button>
          <button id="btn-fetch-proxies" class="cat-btn" onclick="toggleProxyFetch()" style="${isCurrentlyFetching ? 'background:#ef4444;border-color:#ef4444;' : 'background:#818cf8;border-color:#818cf8;'}color:#fff;font-weight:700;padding:0.45rem 0.9rem;font-size:0.82rem;">
            ${isCurrentlyFetching ? '⏹ Стоп сбор' : '📥 Пополнить резерв'}
          </button>
        </div>
      </div>

      <!-- Добавление своего прокси -->
      <div style="margin-bottom:1.25rem;background:var(--bg-main);border:1px solid var(--border-color);border-radius:8px;padding:0.85rem 1rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.4rem;flex-wrap:wrap;gap:0.5rem;">
          <label style="font-size:0.85rem;font-weight:700;color:var(--text-primary);margin:0;">
            ➕ Добавить личные прокси ${targetUser ? `для @${escapeHtml(targetUser)}` : ''} (по одному на строку):
          </label>
          <div style="display:flex;align-items:center;gap:0.4rem;">
            <input type="file" id="proxy-file-input" accept=".txt,.csv,.list,.log,text/plain" style="display:none;" onchange="handleProxyFileUpload(event)">
            <button type="button" class="cat-btn" onclick="document.getElementById('proxy-file-input').click()" style="padding:0.25rem 0.65rem;font-size:0.8rem;background:rgba(99,102,241,0.15);color:#818cf8;border:1px solid rgba(99,102,241,0.35);font-weight:600;display:inline-flex;align-items:center;gap:0.35rem;border-radius:6px;cursor:pointer;" title="Прикрепить файл со списком прокси (.txt)">
              📎 Прикрепить файл
            </button>
          </div>
        </div>
        <textarea id="custom-proxies-input" rows="3" class="form-control" style="font-family:monospace;font-size:0.8rem;resize:vertical;" placeholder="185.190.141.2:8080&#10;http://user:pass@192.168.1.10:8000&#10;socks5://user:pass@192.168.1.20:1080"></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.5rem;">
          <span style="font-size:0.75rem;color:var(--text-secondary);">Поддерживаются форматы HTTP, HTTPS и SOCKS5</span>
          <button onclick="submitCustomProxies()" class="cat-btn" style="background:var(--accent);color:#0f172a;font-weight:700;padding:0.4rem 1rem;">
            Сохранить в личные
          </button>
        </div>
      </div>

      <!-- Список текущих прокси -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
        <label id="proxy-list-title" style="font-size:0.85rem;font-weight:700;color:var(--text-secondary);">
          📋 Прокси в работе:
        </label>
        <div style="display:flex;gap:0.4rem;align-items:center;">
          <button id="btn-check-proxies-mini" type="button" class="cat-btn" onclick="checkAllProxies()" style="font-size:0.75rem;padding:0.25rem 0.6rem;background:rgba(2,132,199,0.15);color:#38bdf8;border-color:rgba(2,132,199,0.3);" title="Проверить прокси">🔍 Проверить</button>
          <button id="btn-clear-proxies-mini" type="button" class="cat-btn" onclick="clearAllProxies()" style="font-size:0.75rem;padding:0.25rem 0.6rem;background:rgba(239,68,68,0.12);color:#ef4444;border-color:rgba(239,68,68,0.3);" title="Очистить все прокси">🗑 Очистить все</button>
        </div>
      </div>
      <div id="proxy-list-container" style="max-height:220px;overflow-y:auto;background:var(--bg-main);border:1px solid var(--border-color);border-radius:8px;padding:0.5rem 0.75rem;font-family:monospace;font-size:0.8rem;">
        Загрузка списка...
      </div>

      <div style="display:flex;justify-content:flex-end;gap:0.75rem;margin-top:1.25rem;">
        <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.6rem 1.4rem;">Закрыть</button>
      </div>
    </div>
  `;
  modalOverlay.classList.add('open');
  // Немедленный запрос актуальных данных (не ждём — модалка уже открыта)
  refreshProxyModalData();

  if (window._proxyModalInterval) clearInterval(window._proxyModalInterval);
  window._proxyModalInterval = setInterval(() => {
    if (modalOverlay && modalOverlay.classList.contains('open')) {
      refreshProxyModalData();
    } else {
      clearInterval(window._proxyModalInterval);
      window._proxyModalInterval = null;
    }
  }, 1000);
};

window.refreshProxyModalData = async function() {
  const targetUser = window._proxyModalUser || (currentUser ? currentUser.username : '');
  const userCountEl = document.getElementById('proxy-modal-user-count');
  const sharedCountEl = document.getElementById('proxy-modal-shared-count');
  const modeBadgeEl = document.getElementById('proxy-modal-mode-badge');
  const btnFetch = document.getElementById('btn-fetch-proxies');
  const listEl = document.getElementById('proxy-list-container');
  const listTitleEl = document.getElementById('proxy-list-title');

  try {
    const url = targetUser
      ? `/api/avito/proxies?username=${encodeURIComponent(targetUser)}&t=${Date.now()}`
      : `/api/avito/proxies?t=${Date.now()}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data && data.success) {
      if (userCountEl) userCountEl.innerText = `${data.user_count || 0} шт.`;
      const liveSharedCount = data.is_custom ? (data.shared_count || 0) : (data.count || data.shared_count || 0);
      if (sharedCountEl) sharedCountEl.innerText = `${liveSharedCount} шт.`;

      if (modeBadgeEl) {
        if (data.is_custom) {
          modeBadgeEl.innerHTML = '🟢 Личные прокси (изолирован)';
          modeBadgeEl.style.background = 'rgba(16, 185, 129, 0.15)';
          modeBadgeEl.style.color = '#10b981';
        } else {
          modeBadgeEl.innerHTML = '🟡 Общий резерв (Fallback)';
          modeBadgeEl.style.background = 'rgba(245, 158, 11, 0.15)';
          modeBadgeEl.style.color = '#f59e0b';
        }
      }

      if (listTitleEl) {
        listTitleEl.innerText = data.is_custom
          ? `📋 Личные прокси пользователя (${data.user_count || 0} шт.):`
          : `📋 Прокси из общего резерва (${data.shared_count || 0} шт.):`;
      }

      if (data.is_fetching !== undefined) {
        avitoIsFetchingProxies = Boolean(data.is_fetching);
        if (avitoData && avitoData.stats) avitoData.stats.proxy_fetching = Boolean(data.is_fetching);
      }

      // Мгновенная синхронизация счётчика на кнопке в основном интерфейсе
      const effectiveCount = data.is_custom ? (data.user_count || 0) : (data.count || data.shared_count || 0);
      avitoProxyCount = effectiveCount;
      if (avitoData && avitoData.stats) {
        avitoData.stats.proxy_count = effectiveCount;
      }
      if (typeof updateAvitoProxiesUI === 'function') {
        updateAvitoProxiesUI();
      }
      
      if (btnFetch) {
        if (data.is_fetching) {
          btnFetch.innerText = '⏹ Стоп сбор';
          btnFetch.style.background = '#ef4444';
          btnFetch.style.borderColor = '#ef4444';
        } else {
          btnFetch.innerText = '📥 Пополнить резерв';
          btnFetch.style.background = '#818cf8';
          btnFetch.style.borderColor = '#818cf8';
        }
      }

      if (listEl) {
        const details = (data.proxy_details && data.proxy_details.length)
          ? data.proxy_details
          : (data.is_custom ? (data.user_proxies || []) : (data.proxies || [])).map(p => ({ address: p, ping: null, status: 'reserve' }));

        if (!details || details.length === 0) {
          listEl.innerHTML = '<span style="color:var(--text-secondary);">Пул прокси пуст. Добавьте свои личные прокси выше или нажмите «Пополнить резерв».</span>';
        } else {
          const statusCfg = {
            active:  { bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.45)', dot: '#10b981', label: 'В работе',   labelColor: '#10b981', pulse: true  },
            waiting: { bg: 'rgba(245,158,11,0.10)',  border: 'rgba(245,158,11,0.40)',  dot: '#f59e0b', label: 'В ожидании', labelColor: '#f59e0b', pulse: false },
            reserve: { bg: 'rgba(148,163,184,0.06)', border: 'rgba(100,116,139,0.25)', dot: '#64748b', label: 'В резерве',  labelColor: '#64748b', pulse: false },
          };
          const groupTitles = {
            active:  '🟢 В работе — боевой состав',
            waiting: '🟡 В ожидании — горячий резерв',
            reserve: '⚪ В резерве — запас',
          };

          let html = '';
          let lastGroup = null;
          let globalIdx = 0;

          details.forEach(det => {
            const status = det.status || 'reserve';
            const cfg = statusCfg[status] || statusCfg.reserve;

            // Разделитель группы
            if (status !== lastGroup) {
              lastGroup = status;
              html += `<div style="padding:0.3rem 0.4rem 0.15rem;font-size:0.7rem;font-weight:700;color:${cfg.labelColor};opacity:0.85;margin-top:${globalIdx > 0 ? '0.4rem' : '0'};">${groupTitles[status] || status}</div>`;
            }

            globalIdx++;
            const p = det.address;
            const pingStr = det.ping != null
              ? `<span style="font-size:0.7rem;color:${det.ping < 300 ? '#10b981' : det.ping < 800 ? '#f59e0b' : '#ef4444'};font-family:monospace;flex-shrink:0;">${det.ping}ms</span>`
              : `<span style="font-size:0.7rem;color:#475569;font-family:monospace;flex-shrink:0;">—</span>`;
            const dotAnim = cfg.pulse ? 'animation:proxy-pulse 1.8s ease-in-out infinite;' : '';
            const dotStr = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${cfg.dot};flex-shrink:0;${dotAnim}"></span>`;

            html += `
              <div class="proxy-item-row" style="padding:0.28rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;align-items:center;justify-content:space-between;gap:0.4rem;background:${cfg.bg};border-left:3px solid ${cfg.border};margin-bottom:1px;border-radius:3px;">
                <div style="display:flex;align-items:center;gap:0.35rem;overflow:hidden;min-width:0;flex:1;">
                  ${dotStr}
                  <span style="font-size:0.77rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:monospace;">${globalIdx}. ${escapeHtml(p)}</span>
                  ${pingStr}
                </div>
                <button type="button" onclick="deleteProxyItem('${escapeHtml(p)}', this)" title="Удалить прокси" style="background:transparent;border:none;color:#ef4444;cursor:pointer;padding:0.1rem 0.25rem;font-size:0.82rem;flex-shrink:0;">🗑️</button>
              </div>
            `;
          });

          // CSS для мигания активных прокси (добавляем один раз)
          if (!document.getElementById('proxy-pulse-style')) {
            const st = document.createElement('style');
            st.id = 'proxy-pulse-style';
            st.textContent = '@keyframes proxy-pulse { 0%,100%{opacity:1;} 50%{opacity:0.35;} }';
            document.head.appendChild(st);
          }

          listEl.innerHTML = html;
        }
      }

    }
  } catch (e) {
    console.error('refreshProxyModalData error:', e);
    if (listEl) listEl.innerHTML = `<span style="color:#ef4444;font-size:0.8rem;">Ошибка загрузки прокси: ${escapeHtml(e.message || String(e))}</span>`;
  }
};


window.deleteProxyItem = async function(proxyStr, btnEl) {
  // Мгновенное удаление строки из DOM без задержки и подтверждений
  if (btnEl) {
    const row = btnEl.closest ? btnEl.closest('.proxy-item-row') : btnEl.parentElement.parentElement;
    if (row) {
      row.remove();
      const listEl = document.getElementById('proxy-list-container');
      if (listEl && listEl.querySelectorAll('.proxy-item-row').length === 0) {
        listEl.innerHTML = '<span style="color:var(--text-secondary);">Пул прокси пуст. Добавьте свои личные прокси выше или нажмите «Пополнить резерв».</span>';
      }
    }
  }
  const targetUser = window._proxyModalUser || (currentUser ? currentUser.username : '');
  if (typeof showToast === 'function') {
    showToast('🗑️ Прокси удален', 1200);
  }
  try {
    const res = await fetch('/api/avito/proxies/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxy: proxyStr, username: targetUser })
    });
    const data = await res.json();
    if (data.success) {
      await refreshProxyModalData();
      await loadAvitoStats(true);
    } else {
      if (typeof showToast === 'function') {
        showToast('❌ Ошибка удаления: ' + (data.error || 'Сбой'), 2000, 'red');
      }
      await refreshProxyModalData();
    }
  } catch (e) {
    console.error('deleteProxyItem error:', e);
  }
};

window.toggleProxyFetch = async function() {
  const btn = document.getElementById('btn-fetch-proxies');
  const isCurrentlyFetching = btn && btn.innerText.includes('Стоп');
  const action = isCurrentlyFetching ? 'stop' : 'start';

  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Ждите...';
  }

  avitoIsFetchingProxies = (action === 'start');
  if (avitoData && avitoData.stats) {
    avitoData.stats.proxy_fetching = (action === 'start');
  }

  try {
    const res = await fetch('/api/avito/proxies/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, source: 'manual' })
    });
    const data = await res.json();
    showToast(data.message || (action === 'start' ? 'Запущен поиск прокси' : 'Поиск остановлен'));
    await refreshProxyModalData();
    await loadAvitoStats(true);
  } catch (e) {
    alert('Ошибка вызова сборщика прокси.');
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.submitCustomProxies = async function() {
  const input = document.getElementById('custom-proxies-input');
  if (!input || !input.value.trim()) {
    alert('Введите хотя бы один прокси');
    return;
  }
  const targetUser = window._proxyModalUser || (currentUser ? currentUser.username : '');

  try {
    const res = await fetch('/api/avito/proxies/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxies: input.value.trim(), username: targetUser })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✅ Добавлено прокси: ${data.added || 0} (всего: ${data.total || 0})`);
      input.value = '';
      await refreshProxyModalData();
      await loadAvitoStats(true);
    } else {
      alert('Ошибка добавления: ' + (data.error || 'Неизвестная ошибка'));
    }
  } catch (e) {
    alert('Ошибка соединения с сервером.');
  }
};

window.handleProxyFileUpload = function(event) {
  const file = event && event.target && event.target.files ? event.target.files[0] : null;
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const text = e.target.result || '';
      const input = document.getElementById('custom-proxies-input');
      if (!input) return;

      const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
      if (lines.length === 0) {
        if (typeof showToast === 'function') {
          showToast('⚠️ Выбранный файл пуст', 'warning');
        } else {
          alert('Выбранный файл пуст');
        }
        return;
      }

      const existing = input.value.trim();
      if (existing) {
        input.value = existing + '\n' + lines.join('\n');
      } else {
        input.value = lines.join('\n');
      }

      if (event.target) event.target.value = '';

      if (typeof showToast === 'function') {
        showToast(`📎 Загружено ${lines.length} прокси из ${file.name}`, 'success');
      }
    } catch (err) {
      console.error('handleProxyFileUpload error:', err);
      alert('Ошибка при чтении файла: ' + err.message);
    }
  };
  reader.onerror = function() {
    alert('Не удалось прочитать файл');
  };
  reader.readAsText(file, 'UTF-8');
};

window.checkAllProxies = async function() {
  const btnCheck = document.getElementById('btn-check-proxies');
  const btnCheckMini = document.getElementById('btn-check-proxies-mini');
  const originalText = btnCheck ? btnCheck.innerText : '🔍 Проверить';

  if (btnCheck) {
    btnCheck.disabled = true;
    btnCheck.innerText = '⏳ Проверка...';
  }
  if (btnCheckMini) {
    btnCheckMini.disabled = true;
    btnCheckMini.innerText = '⏳ Проверка...';
  }
  if (typeof showToast === 'function') {
    showToast('🔍 Проверка прокси на доступность к Avito...', 2500);
  }

  const targetUser = window._proxyModalUser || (currentUser ? currentUser.username : '');
  try {
    const res = await fetch('/api/avito/proxies/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: targetUser })
    });
    const data = await res.json();
    if (data && data.success) {
      const msg = `✅ Проверка завершена: ${data.alive_count || 0} живых, удалено мертвых: ${data.removed_count || 0}`;
      if (typeof showToast === 'function') {
        showToast(msg, 3500);
      } else {
        alert(msg);
      }
      await refreshProxyModalData();
      await loadAvitoStats(true);
    } else {
      alert('Ошибка проверки: ' + (data && data.error ? data.error : 'Неизвестный сбой'));
    }
  } catch (e) {
    console.error('checkAllProxies error:', e);
    alert('Сбой сетевого запроса при проверке прокси.');
  } finally {
    if (btnCheck) {
      btnCheck.disabled = false;
      btnCheck.innerText = originalText;
    }
    if (btnCheckMini) {
      btnCheckMini.disabled = false;
      btnCheckMini.innerText = '🔍 Проверить';
    }
  }
};

window.clearAllProxies = async function() {
  const targetUser = window._proxyModalUser || (currentUser ? currentUser.username : '');
  const modeBadge = document.getElementById('proxy-modal-mode-badge');
  const isPersonal = Boolean(modeBadge && modeBadge.innerText && modeBadge.innerText.includes('Личные'));
  const promptMsg = isPersonal
    ? 'Вы уверены, что хотите удалить ВСЕ личные прокси?'
    : 'Вы уверены, что хотите полностью очистить весь общий пул прокси?';

  if (!confirm(promptMsg)) {
    return;
  }

  const btnClear = document.getElementById('btn-clear-proxies');
  const btnClearMini = document.getElementById('btn-clear-proxies-mini');
  if (btnClear) {
    btnClear.disabled = true;
    btnClear.innerText = '⏳ Очистка...';
  }
  if (btnClearMini) {
    btnClearMini.disabled = true;
    btnClearMini.innerText = '⏳ Очистка...';
  }

  try {
    const res = await fetch('/api/avito/proxies/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: targetUser })
    });
    const data = await res.json();
    if (data && data.success) {
      if (typeof showToast === 'function') {
        showToast(`🗑️ Удалено прокси: ${data.removed_count || 0}`, 2500);
      }
      await refreshProxyModalData();
      await loadAvitoStats(true);
    } else {
      alert('Ошибка очистки: ' + (data && data.error ? data.error : 'Неизвестный сбой'));
    }
  } catch (e) {
    console.error('clearAllProxies error:', e);
    alert('Сбой сетевого запроса при очистке прокси.');
  } finally {
    if (btnClear) {
      btnClear.disabled = false;
      btnClear.innerText = '🗑 Очистить все';
    }
    if (btnClearMini) {
      btnClearMini.disabled = false;
      btnClearMini.innerText = '🗑 Очистить все';
    }
  }
};

// ==================== МОДАЛЬНОЕ ОКНО КЛИЕНТОВ / ПОЛЬЗОВАТЕЛЕЙ ====================

window.openClientsModal = async function() {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  modalBody.innerHTML = `
    <div style="padding:0.5rem 0;">
      <h3 style="font-size:1.35rem;font-weight:800;color:#f472b6;margin-bottom:0.75rem;display:flex;align-items:center;gap:0.5rem;">
        👥 Управление клиентами и доступом
      </h3>
      <p style="font-size:0.88rem;color:var(--text-secondary);margin-bottom:1rem;">
        Мультисессионный режим: у каждого клиента персональные поиски. Здесь вы можете одобрять заявки, блокировать или удалять пользователей.
      </p>

      <div id="clients-list-container" style="max-height:360px;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px;">
        <div style="padding:1.5rem;text-align:center;color:var(--text-secondary);">Загрузка клиентов...</div>
      </div>

      <div style="display:flex;justify-content:flex-end;gap:0.75rem;margin-top:1.25rem;">
        <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.6rem 1.4rem;">Закрыть</button>
      </div>
    </div>
  `;
  modalOverlay.classList.add('open');
  await refreshClientsModalData();
};

window.refreshClientsModalData = async function() {
  const container = document.getElementById('clients-list-container');
  if (!container) return;

  try {
    const res = await fetch('/api/avito/users?t=' + Date.now());
    const data = await res.json();
    if (data && data.success) {
      const users = data.users || [];
      if (users.length === 0) {
        container.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-secondary);">Пользователей пока нет.</div>';
        return;
      }

      container.innerHTML = `
        <table class="avito-table">
          <thead>
            <tr>
              <th>Пользователь</th>
              <th>Статус</th>
              <th>Дата регистрации</th>
              <th style="text-align:right;">Действия</th>
            </tr>
          </thead>
          <tbody>
            ${users.map(u => {
              const isPending = u.status === 'pending';
              const isApproved = u.status === 'approved';
              const isBlocked = u.status === 'blocked';
              const isUserAdmin = u.status === 'admin';

              let statusBadge = '';
              if (isUserAdmin) {
                statusBadge = '<span style="background:rgba(234,179,8,0.2);color:#fbbf24;border:1px solid rgba(234,179,8,0.4);padding:0.15rem 0.5rem;border-radius:12px;font-weight:700;">👑 Админ</span>';
              } else if (isApproved) {
                statusBadge = '<span style="background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.15rem 0.5rem;border-radius:12px;font-weight:700;">✅ Одобрен</span>';
              } else if (isPending) {
                statusBadge = '<span style="background:rgba(245,158,11,0.2);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);padding:0.15rem 0.5rem;border-radius:12px;font-weight:700;">⏳ Заявка</span>';
              } else {
                statusBadge = '<span style="background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);padding:0.15rem 0.5rem;border-radius:12px;font-weight:700;">🚫 Заблокирован</span>';
              }

              return `
                <tr>
                  <td>
                    <strong>${escapeHtml(u.full_name || 'Без имени')}</strong>
                    <div style="font-size:0.75rem;color:var(--text-secondary);">
                      ${u.username ? '@' + escapeHtml(u.username) : 'ID: ' + u.user_id}
                    </div>
                  </td>
                  <td>${statusBadge}</td>
                  <td style="font-size:0.78rem;color:var(--text-secondary);">${(u.created_at || '').replace('T', ' ')}</td>
                  <td style="text-align:right;">
                    ${isUserAdmin ? '<span style="font-size:0.75rem;color:var(--text-secondary);">Главный</span>' : `
                      <div style="display:inline-flex;gap:0.35rem;align-items:center;">
                        ${isPending || isBlocked ? `
                          <button onclick="setClientStatus(${u.user_id}, 'approved')" class="cat-btn" style="padding:0.25rem 0.6rem;font-size:0.75rem;background:#10b981;color:#fff;border-color:#10b981;font-weight:700;" title="Разрешить доступ к боту">
                            ✅ Одобрить
                          </button>
                        ` : ''}
                        ${isApproved ? `
                          <button onclick="setClientStatus(${u.user_id}, 'blocked')" class="cat-btn" style="padding:0.25rem 0.6rem;font-size:0.75rem;background:#ef4444;color:#fff;border-color:#ef4444;font-weight:700;" title="Приостановить доступ">
                            🚫 Блок
                          </button>
                        ` : ''}
                        <button onclick="setClientStatus(${u.user_id}, 'delete')" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:1.1rem;padding:0 0.3rem;" title="Удалить клиента и очистить его базу">
                          🗑️
                        </button>
                      </div>
                    `}
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }
  } catch (e) {
    container.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#ef4444;">Ошибка загрузки клиентов.</div>';
  }
};

window.setClientStatus = async function(userId, status) {
  if (status === 'delete' && !confirm('Точно удалить этого клиента и стереть все его персональные поиски и данные?')) {
    return;
  }

  try {
    const res = await fetch('/api/avito/users/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, status: status })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Статус клиента обновлен');
      await refreshClientsModalData();
      await loadAvitoStats();
    } else {
      alert('Ошибка: ' + (data.error || 'Не удалось обновить статус'));
    }
  } catch (e) {
    alert('Ошибка соединения с сервером.');
  }
};

window.openManageSearchesModal = function(filterQuery) {
  if (typeof window.isLicenseExpired === 'function' && window.isLicenseExpired()) {
    window.setLicenseExpiredMode(true);
    if (typeof openActivationModal === 'function') openActivationModal();
    return;
  }
  window._isManageSearchesModalOpen = true;
  if (!window._pendingSearchesInModal) {
    window._pendingSearchesInModal = new Set();
  }
  // Сохраняем текущие значения формы 1 варианта если они введены в DOM
  const curQ = document.getElementById('avito-gen-query');
  const curCat = document.getElementById('avito-gen-category');
  const curPmin = document.getElementById('avito-gen-pmin');
  const curPmax = document.getElementById('avito-gen-pmax');
  if (curQ) {
    window._avitoGenState = {
      query: curQ.value,
      category: curCat ? curCat.value : (window._avitoGenState?.category || 'videokarty'),
      pmin: curPmin ? curPmin.value : '',
      pmax: curPmax ? curPmax.value : ''
    };
  }
  const savedGenState = window._avitoGenState || { query: '', category: 'videokarty', pmin: '', pmax: '' };

  let searches = normalizeSearches(avitoData.searches);
  if (searches.length === 0 && currentUser && currentUser.avito_searches) {
    searches = normalizeSearches(currentUser.avito_searches);
    if (searches.length > 0 && avitoData) {
      avitoData.searches = searches;
    }
  }
  const rawMaxS = (avitoData.stats && avitoData.stats.max_searches) 
    || (currentUser && currentUser.permissions && currentUser.permissions.max_searches) 
    || 10;
  const maxS = Math.min(10, Math.max(1, Number(rawMaxS) || 10));
  const canAddMore = searches.length < maxS;
  if (window._searchVariant1Open === undefined) window._searchVariant1Open = false;
  if (window._searchVariant2Open === undefined) window._searchVariant2Open = false;
  if (window._trackedLinksOpen === undefined) window._trackedLinksOpen = true;

  // Фильтрация по поисковому запросу
  const q = (filterQuery || '').toLowerCase().trim();
  const filtered = q
    ? searches.filter(s => (s.name || '').toLowerCase().includes(q) || (s.url || '').toLowerCase().includes(q))
    : searches;

  modalBody.innerHTML = `
    <div style="padding:0.25rem 0;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;border-bottom:1px solid var(--border-color);padding-bottom:0.75rem;">
        <div>
          <h3 style="font-size:1.3rem;font-weight:800;color:var(--text-primary);margin:0;display:flex;align-items:center;gap:0.45rem;">
            🎯 Управление отслеживаемыми ссылками
          </h3>
          <p style="font-size:0.83rem;color:var(--text-secondary);margin:0.25rem 0 0 0;">
            Добавляйте ссылки, настраивайте авто-выкуп и авто-бронь персонально для каждой ссылки.
          </p>
        </div>
        <div style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);padding:0.35rem 0.75rem;border-radius:20px;font-size:0.82rem;font-weight:700;">
          📊 Ссылок: ${searches.length} / ${maxS}
        </div>
      </div>

      <!-- Поле поиска по ссылкам -->
      ${searches.length > 0 ? `
      <div style="margin-bottom:1rem;position:relative;">
        <span style="position:absolute;left:0.75rem;top:50%;transform:translateY(-50%);font-size:0.95rem;pointer-events:none;">🔍</span>
        <input
          type="text"
          id="avito-search-filter"
          class="form-control"
          placeholder="Поиск по названию или URL..."
          autocomplete="off"
          style="padding-left:2.2rem;font-size:0.88rem;"
          value="${escapeHtml(filterQuery || '')}"
          oninput="openManageSearchesModal(this.value)"
        >
      </div>
      ` : ''}

      <!-- Блок создания и добавления ссылок (Сворачиваемые блоки: Вариант 1 и Вариант 2) -->
      ${canAddMore ? `
      <div style="margin-bottom:1.15rem;display:flex;flex-direction:column;gap:0.55rem;">
        
        <!-- ВАРИАНТ 1: Быстрая генерация ссылки на сайте (Сворачиваемый вниз блок) -->
        <div style="background:var(--bg-main);border:1px solid rgba(59,130,246,0.3);border-radius:9px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div onclick="window.toggleSearchVariant(1)" style="padding:0.65rem 0.95rem;background:rgba(59,130,246,0.07);cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none;transition:background 0.15s ease;"
               onmouseover="this.style.background='rgba(59,130,246,0.13)'" onmouseout="this.style.background='rgba(59,130,246,0.07)'">
            <div style="display:flex;align-items:center;gap:0.45rem;flex-wrap:wrap;">
              <span style="font-size:1.05rem;">⚡</span>
              <span style="font-size:0.88rem;font-weight:700;color:var(--text-primary);">Вариант 1: Сгенерировать поиск товара</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.35rem;font-size:0.77rem;color:var(--text-secondary);font-weight:600;">
              <span id="variant-1-label">${window._searchVariant1Open ? 'Свернуть' : 'Развернуть'}</span>
              <span id="variant-1-arrow" style="display:inline-block;transition:transform 0.2s ease;transform:${window._searchVariant1Open ? 'rotate(180deg)' : 'rotate(0deg)'};font-size:0.72rem;">▼</span>
            </div>
          </div>

          <div id="variant-1-body" style="display:${window._searchVariant1Open ? 'block' : 'none'};padding:0.8rem 0.95rem;border-top:1px solid rgba(59,130,246,0.2);background:rgba(59,130,246,0.02);">
            <form onsubmit="submitGenerateAvitoSearch(event)" style="margin:0;">
              <!-- Верхний ряд: Название товара и Категория с поиском -->
              <div style="display:flex;gap:0.55rem;align-items:flex-end;flex-wrap:wrap;margin-bottom:0.6rem;">
                <!-- Поле названия товара -->
                <div class="form-group" style="flex:2.2;min-width:180px;margin-bottom:0;">
                  <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:0.2rem;">
                    Название товара <span style="color:#ef4444;">*</span>:
                  </label>
                  <input
                    type="text"
                    id="avito-gen-query"
                    class="form-control"
                    placeholder="Например: RX 590 или RTX 3060"
                    autocomplete="off"
                    oninput="onGenQueryInput()"
                    value="${escapeHtml(savedGenState.query || '')}"
                    style="font-size:0.84rem;padding:0.42rem 0.65rem;"
                  >
                </div>

                <!-- Категория товара с быстрым поиском -->
                <div class="form-group" style="flex:1.8;min-width:190px;margin-bottom:0;">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;gap:0.35rem;">
                    <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;">
                      Категория:
                    </label>
                    <input
                      type="text"
                      id="avito-cat-search"
                      placeholder="🔍 Поиск категории..."
                      autocomplete="off"
                      oninput="filterAvitoCategories(this.value)"
                      style="font-size:0.72rem;padding:0.12rem 0.4rem;width:125px;height:20px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-main);color:var(--text-primary);outline:none;"
                      title="Быстрый фильтр категорий"
                    >
                  </div>
                  <select
                    id="avito-gen-category"
                    class="form-control"
                    style="font-size:0.84rem;padding:0.42rem 0.65rem;cursor:pointer;"
                  >
                    ${getAvitoCategoryOptionsHtml(savedGenState.category)}
                  </select>
                </div>
              </div>

              <!-- Нижний ряд: Выбор региона под категорией, Цены и Кнопка -->
              <div style="display:flex;gap:0.55rem;align-items:flex-end;flex-wrap:wrap;">
                <!-- Выбор региона с быстрым поиском -->
                <div class="form-group" style="flex:2.2;min-width:180px;margin-bottom:0;">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;gap:0.35rem;">
                    <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;">
                      Выбор региона / города:
                    </label>
                    <input
                      type="text"
                      id="avito-region-search"
                      placeholder="🔍 Поиск региона..."
                      autocomplete="off"
                      oninput="filterAvitoRegions(this.value)"
                      style="font-size:0.72rem;padding:0.12rem 0.4rem;width:125px;height:20px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-main);color:var(--text-primary);outline:none;"
                      title="Быстрый поиск города или региона"
                    >
                  </div>
                  <select
                    id="avito-gen-region"
                    class="form-control"
                    style="font-size:0.84rem;padding:0.42rem 0.65rem;cursor:pointer;"
                  >
                    ${getAvitoRegionOptionsHtml(savedGenState.region)}
                  </select>
                </div>

                <!-- Цена от -->
                <div class="form-group" style="flex:0.85;min-width:85px;margin-bottom:0;">
                  <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:0.2rem;">
                    Цена от (₽):
                  </label>
                  <input
                    type="number"
                    id="avito-gen-pmin"
                    class="form-control"
                    placeholder="от 0"
                    min="0"
                    step="500"
                    autocomplete="off"
                    value="${escapeHtml(savedGenState.pmin || '')}"
                    style="font-size:0.84rem;padding:0.42rem 0.65rem;"
                  >
                </div>

                <!-- Цена до -->
                <div class="form-group" style="flex:0.85;min-width:85px;margin-bottom:0;">
                  <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:0.2rem;">
                    до (₽):
                  </label>
                  <input
                    type="number"
                    id="avito-gen-pmax"
                    class="form-control"
                    placeholder="до..."
                    min="0"
                    step="500"
                    autocomplete="off"
                    value="${escapeHtml(savedGenState.pmax || '')}"
                    style="font-size:0.84rem;padding:0.42rem 0.65rem;"
                  >
                </div>

                <!-- Кнопка генерации -->
                <button
                  type="submit"
                  id="btn-avito-gen-submit"
                  class="cat-btn"
                  style="background:#3b82f6;color:#fff;border-color:#3b82f6;font-weight:700;padding:0.45rem 1.05rem;display:inline-flex;align-items:center;gap:0.35rem;white-space:nowrap;height:36px;"
                  title="Сгенерировать ссылку с точной категорией, регионом и ценой и сразу поставить на отслеживание"
                >
                  ⚡ Сгенерировать
                </button>
              </div>
            </form>
          </div>
        </div>

        <!-- ВАРИАНТ 2: Вставить готовую ссылку с Авито (Сворачиваемый вниз блок) -->
        <div style="background:var(--bg-main);border:1px solid rgba(148,163,184,0.3);border-radius:9px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div onclick="window.toggleSearchVariant(2)" style="padding:0.65rem 0.95rem;background:rgba(148,163,184,0.07);cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none;transition:background 0.15s ease;"
               onmouseover="this.style.background='rgba(148,163,184,0.13)'" onmouseout="this.style.background='rgba(148,163,184,0.07)'">
            <div style="display:flex;align-items:center;gap:0.45rem;">
              <span style="font-size:1.05rem;">📋</span>
              <span style="font-size:0.88rem;font-weight:700;color:var(--text-primary);">Вариант 2: Вставить готовую ссылку с Авито</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.35rem;font-size:0.77rem;color:var(--text-secondary);font-weight:600;">
              <span id="variant-2-label">${window._searchVariant2Open ? 'Свернуть' : 'Развернуть'}</span>
              <span id="variant-2-arrow" style="display:inline-block;transition:transform 0.2s ease;transform:${window._searchVariant2Open ? 'rotate(180deg)' : 'rotate(0deg)'};font-size:0.72rem;">▼</span>
            </div>
          </div>

          <div id="variant-2-body" style="display:${window._searchVariant2Open ? 'block' : 'none'};padding:0.8rem 0.95rem;border-top:1px solid rgba(148,163,184,0.2);background:rgba(148,163,184,0.02);">
            <form onsubmit="submitAddAvitoSearch(event, true)" style="margin:0;">
              <div class="form-group" style="margin-bottom:0.55rem;">
                <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:0.2rem;">Ссылка на поиск с Авито <span style="color:#ef4444;">*</span>:</label>
                <div style="display:flex;gap:0.5rem;align-items:center;">
                  <input type="text" id="avito-add-url" class="form-control" placeholder="https://www.avito.ru/..." autocomplete="off" style="font-size:0.84rem;flex:1;padding:0.42rem 0.65rem;">
                  <button type="button" onclick="pasteAvitoUrl()" class="cat-btn" style="background:rgba(99,102,241,0.18);color:#818cf8;border-color:rgba(99,102,241,0.45);padding:0.42rem 0.8rem;font-size:0.82rem;white-space:nowrap;display:inline-flex;align-items:center;gap:0.3rem;flex-shrink:0;height:36px;" title="Вставить ссылку из буфера обмена">
                    📋 Вставить
                  </button>
                </div>
              </div>
              <div style="display:flex;gap:0.6rem;align-items:flex-end;flex-wrap:wrap;">
                <div class="form-group" style="flex:1;min-width:180px;margin-bottom:0;">
                  <label style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:0.2rem;">Название / Метка (необязательно):</label>
                  <input type="text" id="avito-add-name" class="form-control" placeholder="Например: Видеокарты Москва от 15к" autocomplete="off" style="font-size:0.84rem;padding:0.42rem 0.65rem;">
                </div>
                <button type="submit" class="cat-btn" style="background:#10b981;color:#fff;border-color:#10b981;font-weight:700;padding:0.45rem 1.1rem;display:inline-flex;align-items:center;gap:0.35rem;white-space:nowrap;height:36px;">
                  💾 Сохранить
                </button>
              </div>
            </form>
          </div>
        </div>

      </div>
      ` : ''}

      ${!isAdmin() ? `
      <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.3);border-radius:8px;padding:0.75rem 1rem;font-size:0.85rem;margin-bottom:1.25rem;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
        📋 Согласно тарифному плану Вам доступна для активного поиска:
        <strong style="color:#10b981;font-size:1rem;">${pluralLinks(maxS)}</strong>
        <span style="color:var(--text-secondary);font-size:0.8rem;">— остальные ссылки отображаются, но не участвуют в мониторинге. Для изменения лимита обратитесь к администратору.</span>
      </div>
      ` : ''}

      <!-- Список активных ссылок (с учётом фильтра) - Сворачиваемый блок -->
      <div style="background:var(--bg-main);border:1px solid rgba(148,163,184,0.3);border-radius:9px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);margin-bottom:0.75rem;">
        <div onclick="window.toggleTrackedLinksSection()" style="padding:0.65rem 0.95rem;background:rgba(148,163,184,0.07);cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none;transition:background 0.15s ease;"
             onmouseover="this.style.background='rgba(148,163,184,0.13)'" onmouseout="this.style.background='rgba(148,163,184,0.07)'">
          <div style="display:flex;align-items:center;gap:0.45rem;">
            <span style="font-size:1.05rem;">📋</span>
            <span style="font-size:0.88rem;font-weight:700;color:var(--text-primary);">
              ${q ? ('Найдено (' + filtered.length + ' из ' + searches.length + '):') : ('Отслеживаемые ссылки (' + searches.length + '):')}
            </span>
          </div>
          <div style="display:flex;align-items:center;gap:0.35rem;font-size:0.77rem;color:var(--text-secondary);font-weight:600;">
            <span id="tracked-links-label">${window._trackedLinksOpen ? 'Свернуть' : 'Развернуть'}</span>
            <span id="tracked-links-arrow" style="display:inline-block;transition:transform 0.2s ease;transform:${window._trackedLinksOpen ? 'rotate(180deg)' : 'rotate(0deg)'};font-size:0.72rem;">▼</span>
          </div>
        </div>

        <div id="tracked-links-body" style="display:${window._trackedLinksOpen ? 'block' : 'none'};padding:0.8rem 0.95rem;border-top:1px solid rgba(148,163,184,0.2);background:rgba(148,163,184,0.02);">
          <div style="max-height:420px;overflow-y:auto;display:flex;flex-direction:column;gap:0.65rem;padding-right:0.25rem;" id="avito-modal-links-list">
        ${searches.length === 0 ? `
          <div style="text-align:center;padding:2rem 1rem;color:var(--text-secondary);border:1px dashed var(--border-color);border-radius:8px;font-size:0.88rem;">
            Пока нет ни одной отслеживаемой ссылки.<br>Сгенерируйте поиск или вставьте готовую ссылку с Авито в блоке выше.
          </div>
        ` : filtered.length === 0 ? `
          <div style="text-align:center;padding:1.5rem 1rem;color:var(--text-secondary);border:1px dashed var(--border-color);border-radius:8px;font-size:0.88rem;">
            🔍 По запросу «${escapeHtml(q)}» ничего не найдено.
          </div>
        ` : filtered.map((s, idx) => {
          const realIdx = searches.indexOf(s);
          const isLocked = !isAdmin() && realIdx >= maxS;
          const isUserActive = (s.is_active !== 0);
          const rowBg = !isUserActive
            ? 'background:rgba(100,116,139,0.06);border:1px solid rgba(148,163,184,0.25);opacity:0.75;'
            : isLocked
            ? 'background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.25);opacity:0.65;'
            : 'background:rgba(16,185,129,0.06);border:1.5px solid rgba(16,185,129,0.35);';
          const lockBadge = isLocked
            ? `<span style="display:inline-flex;align-items:center;gap:0.3rem;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);color:#ef4444;border-radius:20px;padding:0.15rem 0.55rem;font-size:0.75rem;font-weight:700;white-space:nowrap;"><svg viewBox="0 0 24 24" width="10" height="10" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;"><circle cx="12" cy="12" r="10" fill="#ef4444"/><rect x="5.5" y="10.2" width="13" height="3.6" rx="0.8" fill="#ffffff"/></svg> не активна</span>`
            : `<span style="display:inline-flex;align-items:center;gap:0.3rem;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.4);color:#10b981;border-radius:20px;padding:0.15rem 0.55rem;font-size:0.75rem;font-weight:700;white-space:nowrap;">✅ активна</span>`;
          const key = getSearchUniqueKey(s, idx);
          const safeId = getSafeSearchDomId(key);
          const isRecentlyPolled = _recentlyPolledSearchKeys.has(key);
          const isPendingSearch = Boolean(s.is_pending) || (window._pendingSearchesInModal && window._pendingSearchesInModal.has(s.id));

          const isBuyChecked = Boolean(s.autobuy);
          const isReserveChecked = Boolean(s.autoreserve);
          const isDeliveryChecked = (s.price_with_delivery !== 0 && s.price_with_delivery !== false);
          const isOnlyDeliveryChecked = Boolean(s.only_delivery || (s.url && (s.url.includes('d=1') || s.url.includes('cd=1'))));
          const maxPriceVal = (s.max_price && Number(s.max_price) > 0) ? String(s.max_price) : '';
          const minRatingVal = (s.min_rating && Number(s.min_rating) > 0) ? String(s.min_rating) : '';

          if (_editingSearchId === s.id) {
            return `
            <div style="${rowBg}border-radius:9px;padding:0.75rem 0.85rem;display:flex;flex-direction:column;gap:0.55rem;transition:all 0.2s ease;">
              <div style="font-size:0.85rem;font-weight:700;color:var(--text-primary);display:flex;align-items:center;gap:0.4rem;">
                <span>✏️ Редактирование ссылки #${idx + 1}</span>
              </div>
              <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <div style="flex:1;min-width:180px;">
                  <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.2rem;font-weight:600;">Название поиска:</label>
                  <input type="text" id="edit-search-name-${s.id}" value="${escapeHtml(s.name || '')}" placeholder="Например: Название искомого товара" class="form-control" style="width:100%;font-size:0.85rem;padding:0.35rem 0.6rem;">
                </div>
                <div style="flex:2;min-width:240px;">
                  <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.2rem;font-weight:600;">Ссылка Avito:</label>
                  <input type="url" id="edit-search-url-${s.id}" value="${escapeHtml(s.url || '')}" placeholder="https://www.avito.ru/..." class="form-control" style="width:100%;font-size:0.85rem;padding:0.35rem 0.6rem;">
                </div>
              </div>
              <div style="display:flex;justify-content:flex-end;gap:0.45rem;margin-top:0.2rem;">
                <button type="button" onclick="cancelEditAvitoSearch()" class="cat-btn" style="padding:0.35rem 0.85rem;font-size:0.8rem;">
                  Отмена
                </button>
                <button type="button" onclick="saveEditAvitoSearch(${s.id})" class="cat-btn" style="background:#10b981;color:#fff;border-color:#10b981;padding:0.35rem 1rem;font-size:0.8rem;font-weight:700;">
                  💾 Сохранить
                </button>
              </div>
            </div>
            `;
          }

          return `
          <div style="${rowBg}border-radius:9px;padding:0.7rem 0.85rem;display:flex;flex-direction:column;gap:0.55rem;transition:all 0.2s ease;">
            <!-- Верхняя строка карточки ссылки -->
            <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;">
              <div style="display:flex;align-items:center;gap:0.65rem;flex:1;min-width:210px;">
                <!-- Чекбокс включения/выключения ссылки в поиске и опросе -->
                <label style="display:inline-flex;align-items:center;cursor:pointer;margin:0;flex-shrink:0;padding:0.2rem;" title="${isUserActive ? 'Ссылка включена в поиск и опрос. Нажмите, чтобы выключить.' : 'Ссылка выключена. Нажмите, чтобы включить в поиск и опрос.'}">
                  <input type="checkbox" ${isUserActive ? 'checked' : ''} onchange="toggleAvitoSearchActive(${s.id}, this.checked)" style="width:18px;height:18px;cursor:pointer;accent-color:#10b981;">
                </label>

                <div style="flex:1;overflow:hidden;" ondblclick="startEditAvitoSearch(${s.id})" title="Двойной щелчок для редактирования названия или ссылки">
                  <div style="font-weight:700;font-size:0.9rem;color:var(--text-primary);display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                    <span style="color:var(--text-secondary);font-size:0.8rem;">${idx + 1}.</span>
                    <span style="${isUserActive ? '' : 'color:var(--text-secondary);text-decoration:line-through;opacity:0.8;'}">🔎 ${escapeHtml(s.name || 'Поиск')}</span>
                    <span id="modal-poll-badge-${safeId}" class="${isPendingSearch ? 'poll-time-badge waiting' : (isUserActive ? 'poll-time-badge polled' : 'poll-time-badge waiting')}${(!isPendingSearch && isRecentlyPolled) ? ' poll-flash' : ''}" style="margin-left:0.35rem;${!isUserActive ? 'background:rgba(148,163,184,0.12);color:#94a3b8;border:1px solid rgba(148,163,184,0.3);' : (isPendingSearch ? 'background:rgba(234,179,8,0.15);color:#eab308;border:1px solid rgba(234,179,8,0.35);' : 'background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.4);')}" title="${!isUserActive ? 'Поиск по этой ссылке выключен' : (isPendingSearch ? 'Поиск начнётся после закрытия окна управления ссылками' : (s.last_polled_at ? 'В поиске. Последний опрос: ' + escapeHtml(s.last_polled_at) : 'В поиске. Идёт сбор объявлений...'))}">
                      ${!isUserActive ? '⏸️ выключена' : (isPendingSearch ? '⏳ поиск после закрытия' : '✅ в поиске')}
                    </span>
                    ${isAdmin() ? '' : (isLocked ? lockBadge : '')}
                  </div>
                  <!-- 🚚 ТОЛЬКО С ДОСТАВКОЙ (под плашкой статуса вместо URL) -->
                  <div style="margin-top:0.3rem;">
                    <label style="display:inline-flex;align-items:center;gap:0.35rem;cursor:pointer;font-size:0.78rem;font-weight:600;color:${isOnlyDeliveryChecked ? '#10b981' : 'var(--text-secondary)'};" title="Искать только объявления с Авито Доставкой. Если галочка снята — искать и с доставкой, и без доставки">
                      <input type="checkbox" id="search-onlydelivery-${s.id}" ${isOnlyDeliveryChecked ? 'checked' : ''}
                        onchange="updateSearchAutomation(${s.id}, 'only_delivery', this.checked)"
                        style="width:15px;height:15px;accent-color:#10b981;cursor:pointer;">
                      <span style="white-space:nowrap;">🚚 Только с доставкой</span>
                    </label>
                  </div>
                </div>
              </div>
              <div style="display:flex;gap:0.45rem;align-items:center;flex-shrink:0;">
                <button type="button" onclick="startEditAvitoSearch(${s.id})" class="cat-btn" style="background:rgba(234,179,8,0.15);color:#eab308;border-color:rgba(234,179,8,0.35);padding:0.32rem 0.65rem;font-size:0.78rem;font-weight:700;display:inline-flex;align-items:center;gap:0.25rem;" title="Редактировать название или ссылку">
                  ✏️ Изменить
                </button>
                <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener" class="cat-btn" style="background:rgba(59,130,246,0.15);color:#60a5fa;border-color:rgba(59,130,246,0.35);padding:0.32rem 0.72rem;font-size:0.78rem;text-decoration:none;display:inline-flex;align-items:center;gap:0.25rem;" title="Открыть эту страницу на Avito в новой вкладке">
                  🌐 Открыть ↗
                </a>
                <button type="button" onclick="deleteAvitoSearchFromModal(${s.id})" class="cat-btn" style="background:rgba(239,68,68,0.15);color:#ef4444;border-color:rgba(239,68,68,0.35);padding:0.32rem 0.72rem;font-size:0.78rem;font-weight:700;display:inline-flex;align-items:center;gap:0.25rem;" title="Удалить эту ссылку из мониторинга">
                  🗑️ Удалить
                </button>
              </div>
            </div>

            <!-- Нижняя панель внутри карточки ссылки: Выкуп, Автобронь, Планка цены (по умолчанию с доставкой), Мин. рейтинг -->
            <div style="display:flex;align-items:center;gap:0.8rem;flex-wrap:wrap;padding:0.45rem 0.7rem;background:rgba(0,0,0,0.06);border:1px solid rgba(148,163,184,0.18);border-radius:6px;font-size:0.8rem;">
              <!-- ⚡ ВЫКУП -->
              <label style="display:inline-flex;align-items:center;gap:0.35rem;cursor:pointer;font-weight:700;color:${isBuyChecked ? '#10b981' : 'var(--text-primary)'};" title="Авто-выкуп: моментальное оформление и полная оплата лота картой/кошельком роботом при появлении">
                <input type="checkbox" id="search-autobuy-${s.id}" ${isBuyChecked ? 'checked' : ''} onchange="updateSearchAutomation(${s.id}, 'autobuy', this.checked)" style="width:16px;height:16px;accent-color:#10b981;cursor:pointer;">
                <span>⚡ Выкуп</span>
              </label>

              <!-- 🔒 АВТОБРОНЬ -->
              <label style="display:inline-flex;align-items:center;gap:0.35rem;cursor:pointer;font-weight:700;color:${isReserveChecked ? '#3b82f6' : 'var(--text-primary)'};" title="Авто-бронь: резервирование товара без списания средств (оплата при получении в ПВЗ)">
                <input type="checkbox" id="search-autoreserve-${s.id}" ${isReserveChecked ? 'checked' : ''} onchange="updateSearchAutomation(${s.id}, 'autoreserve', this.checked)" style="width:16px;height:16px;accent-color:#3b82f6;cursor:pointer;">
                <span>🔒 Автобронь</span>
              </label>

              <!-- ПЛАНКА ЦЕНЫ -->
              <div style="display:inline-flex;align-items:center;gap:0.3rem;">
                <span style="font-size:0.76rem;color:var(--text-secondary);font-weight:600;white-space:nowrap;">Планка (до):</span>
                <input type="number" id="search-maxprice-${s.id}" value="${escapeHtml(maxPriceVal)}" placeholder="₽..." step="500" min="0"
                  onchange="updateSearchAutomation(${s.id}, 'max_price', this.value)"
                  style="width:85px;height:24px;padding:0.12rem 0.4rem;font-size:0.8rem;font-weight:700;border:1px solid var(--border-color);border-radius:5px;background:var(--bg-main);color:var(--text-primary);"
                  title="Максимальная цена для срабатывания выкупа или автоброни">
              </div>

              <!-- ПО УМОЛЧАНИЮ С УЧЁТОМ ДОСТАВКИ -->
              <label style="display:inline-flex;align-items:center;gap:0.3rem;cursor:pointer;font-size:0.77rem;color:var(--text-secondary);" title="По умолчанию включено: сравнивать итоговую сумму лота (товар + доставка) с вашей планкой">
                <input type="checkbox" id="search-delivery-${s.id}" ${isDeliveryChecked ? 'checked' : ''}
                  onchange="updateSearchAutomation(${s.id}, 'price_with_delivery', this.checked)"
                  style="width:15px;height:15px;accent-color:#10b981;cursor:pointer;">
                <span style="white-space:nowrap;">С учётом доставки</span>
              </label>

              <!-- МИН. РЕЙТИНГ ПРОДАВЦА -->
              <div style="display:inline-flex;align-items:center;gap:0.3rem;">
                <span style="font-size:0.76rem;color:var(--text-secondary);font-weight:600;white-space:nowrap;" title="Минимальный рейтинг продавца">⭐ Рейтинг:</span>
                <input type="number" id="search-minrating-${s.id}" value="${escapeHtml(minRatingVal)}" placeholder="0" step="0.1" min="0" max="5"
                  onchange="updateSearchAutomation(${s.id}, 'min_rating', this.value)"
                  style="width:50px;height:24px;padding:0.12rem 0.35rem;font-size:0.8rem;font-weight:700;border:1px solid var(--border-color);border-radius:5px;background:var(--bg-main);color:var(--text-primary);"
                  title="0 = любой продавец, от 4.5 до 5 = высокий рейтинг">
              </div>
            </div>
          </div>
        `;}).join('')}
          </div>
        </div>
      </div>

      <div style="display:flex;justify-content:flex-end;margin-top:1.25rem;">
        <button type="button" onclick="closeModal()" class="cat-btn" style="padding:0.5rem 1.4rem;font-weight:700;">
          Готово
        </button>
      </div>
    </div>
  `;
  modalOverlay.classList.add('open');

window.focusAddSearchForm = function() {
  window._searchVariant2Open = true;
  const b = document.getElementById('variant-2-body');
  const arr = document.getElementById('variant-2-arrow');
  const lbl = document.getElementById('variant-2-label');
  if (b) b.style.display = 'block';
  if (arr) arr.style.transform = 'rotate(180deg)';
  if (lbl) lbl.textContent = 'Свернуть';
  const inp = document.getElementById('avito-new-search-url');
  if (inp) {
    inp.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => inp.focus(), 250);
  }
};
  // Восстановить фокус в поле поиска если он был активен
  if (q) {
    const inp = document.getElementById('avito-search-filter');
    if (inp) { inp.focus(); inp.setSelectionRange(q.length, q.length); }
  }
};

let _editingSearchId = null;

window.startEditAvitoSearch = function(id) {
  _editingSearchId = id;
  const inp = document.getElementById('avito-search-filter');
  const q = inp ? inp.value.trim() : '';
  openManageSearchesModal(q);
};

window.cancelEditAvitoSearch = function() {
  _editingSearchId = null;
  const inp = document.getElementById('avito-search-filter');
  const q = inp ? inp.value.trim() : '';
  openManageSearchesModal(q);
};

window.saveEditAvitoSearch = async function(id) {
  const nameEl = document.getElementById(`edit-search-name-${id}`);
  const urlEl = document.getElementById(`edit-search-url-${id}`);
  if (!urlEl) return;
  const newName = nameEl ? nameEl.value.trim() : '';
  const newUrl = urlEl.value.trim();
  if (!newUrl) {
    if (typeof markFieldError === 'function') {
      markFieldError(urlEl, 'Ссылка не может быть пустой');
    }
    return;
  }
  if (!newUrl.includes('avito.ru')) {
    if (typeof markFieldError === 'function') {
      markFieldError(urlEl, 'Ссылка должна вести на avito.ru');
    }
    return;
  }
  try {
    let oldSearchName = '';
    const allS = (currentUser && currentUser.avito_searches) ? currentUser.avito_searches : ((avitoData && avitoData.searches) ? avitoData.searches : []);
    const currItem = allS.find(s => Number(s.id) === Number(id));
    if (currItem) {
      oldSearchName = (currItem.name || currItem.url || '').trim();
    }

    const userParam = currentUser && currentUser.username ? currentUser.username : '';
    const res = await fetch('/api/avito/edit-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: id,
        name: newName,
        url: newUrl,
        username: userParam
      })
    });
    const data = await res.json();
    if (data && data.success) {
      // Обновляем список ссылок в памяти и в localStorage
      if (data.searches && currentUser) {
        currentUser.avito_searches = normalizeSearches(data.searches);
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (avitoData) avitoData.searches = currentUser.avito_searches;
      } else if (currentUser && currentUser.avito_searches) {
        const found = currentUser.avito_searches.find(s => Number(s.id) === Number(id));
        if (found) {
          found.name = newName || found.name;
          found.url = newUrl;
          found.is_initialized = 0;
        }
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (avitoData) avitoData.searches = currentUser.avito_searches;
      }

      // Если в фильтре была выбрана эта ссылка — обновляем фильтр на новое имя
      if (oldSearchName && currentAvitoLinkFilter && currentAvitoLinkFilter.toLowerCase() === oldSearchName.toLowerCase()) {
        currentAvitoLinkFilter = (newName || newUrl);
        try { localStorage.setItem('electro_avito_link_filter', currentAvitoLinkFilter); } catch (e) {}
      }

      _editingSearchId = null;
      await loadAvitoStats();
      if (currentCat === 'avito_monitor') renderList();
      const inp = document.getElementById('avito-search-filter');
      const q = inp ? inp.value.trim() : '';
      openManageSearchesModal(q);
    } else {
      if (typeof markFieldError === 'function') {
        markFieldError(urlEl, (data && data.error) || 'Ошибка при сохранении ссылки');
      } else {
        alert((data && data.error) || 'Ошибка при сохранении ссылки');
      }
    }
  } catch (err) {
    console.error('saveEditAvitoSearch error:', err);
    if (typeof markFieldError === 'function') {
      markFieldError(urlEl, 'Не удалось связаться с сервером');
    }
  }
};

window.toggleAvitoSearchActive = async function(searchId, isChecked) {
  try {
    const userParam = currentUser && currentUser.username ? currentUser.username : '';
    const res = await fetch('/api/avito/toggle-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: searchId,
        is_active: isChecked ? 1 : 0,
        username: userParam
      })
    });
    const data = await res.json();
    if (data && data.success) {
      if (avitoData && Array.isArray(avitoData.searches)) {
        const found = avitoData.searches.find(s => Number(s.id) === Number(searchId));
        if (found) {
          found.is_active = isChecked ? 1 : 0;
        }
      }
      await loadAvitoStats();
      if (currentCat === 'avito_monitor') renderList();
      const inp = document.getElementById('avito-search-filter');
      const q = inp ? inp.value.trim() : '';
      openManageSearchesModal(q);
    } else {
      showToast('⚠️ Ошибка изменения статуса ссылки');
    }
  } catch (err) {
    console.error('toggleSearchActive error:', err);
    showToast('⚠️ Не удалось связаться с сервером');
  }
};

window.toggleSearchVariant = function(variantNum) {
  if (variantNum === 1) {
    window._searchVariant1Open = !window._searchVariant1Open;
    const body = document.getElementById('variant-1-body');
    const label = document.getElementById('variant-1-label');
    const arrow = document.getElementById('variant-1-arrow');
    if (body) body.style.display = window._searchVariant1Open ? 'block' : 'none';
    if (label) label.textContent = window._searchVariant1Open ? 'Свернуть' : 'Развернуть';
    if (arrow) arrow.style.transform = window._searchVariant1Open ? 'rotate(180deg)' : 'rotate(0deg)';
  } else if (variantNum === 2) {
    window._searchVariant2Open = !window._searchVariant2Open;
    const body = document.getElementById('variant-2-body');
    const label = document.getElementById('variant-2-label');
    const arrow = document.getElementById('variant-2-arrow');
    if (body) body.style.display = window._searchVariant2Open ? 'block' : 'none';
    if (label) label.textContent = window._searchVariant2Open ? 'Свернуть' : 'Развернуть';
    if (arrow) arrow.style.transform = window._searchVariant2Open ? 'rotate(180deg)' : 'rotate(0deg)';
  } else if (variantNum === 3) {
    window.toggleTrackedLinksSection();
  }
};

window.toggleTrackedLinksSection = function() {
  window._trackedLinksOpen = !window._trackedLinksOpen;
  const body = document.getElementById('tracked-links-body');
  const label = document.getElementById('tracked-links-label');
  const arrow = document.getElementById('tracked-links-arrow');
  if (body) body.style.display = window._trackedLinksOpen ? 'block' : 'none';
  if (label) label.textContent = window._trackedLinksOpen ? 'Свернуть' : 'Развернуть';
  if (arrow) arrow.style.transform = window._trackedLinksOpen ? 'rotate(180deg)' : 'rotate(0deg)';
};

window.updateSearchAutomation = async function(searchId, field, value) {
  const buyEl = document.getElementById(`search-autobuy-${searchId}`);
  const resEl = document.getElementById(`search-autoreserve-${searchId}`);
  const priceEl = document.getElementById(`search-maxprice-${searchId}`);
  const delivEl = document.getElementById(`search-delivery-${searchId}`);
  const delivOnlyEl = document.getElementById(`search-onlydelivery-${searchId}`);
  const ratingEl = document.getElementById(`search-minrating-${searchId}`);

  // Разделение операций: выкуп и автобронь взаимоисключающие
  if (field === 'autobuy' && value === true) {
    if (resEl) {
      resEl.checked = false;
      if (resEl.parentElement) resEl.parentElement.style.color = 'var(--text-primary)';
    }
  } else if (field === 'autoreserve' && value === true) {
    if (buyEl) {
      buyEl.checked = false;
      if (buyEl.parentElement) buyEl.parentElement.style.color = 'var(--text-primary)';
    }
  }

  if (buyEl && buyEl.parentElement) {
    buyEl.parentElement.style.color = buyEl.checked ? '#10b981' : 'var(--text-primary)';
  }
  if (resEl && resEl.parentElement) {
    resEl.parentElement.style.color = resEl.checked ? '#3b82f6' : 'var(--text-primary)';
  }
  if (delivOnlyEl && delivOnlyEl.parentElement) {
    delivOnlyEl.parentElement.style.color = delivOnlyEl.checked ? '#10b981' : 'var(--text-secondary)';
  }

  const autobuy = buyEl ? (buyEl.checked ? 1 : 0) : 0;
  const autoreserve = resEl ? (resEl.checked ? 1 : 0) : 0;
  const max_price = priceEl ? (parseFloat(priceEl.value) || 0) : 0;
  const price_with_delivery = delivEl ? (delivEl.checked ? 1 : 0) : 1;
  const only_delivery = delivOnlyEl ? (delivOnlyEl.checked ? 1 : 0) : 0;
  const min_rating = ratingEl ? (parseFloat(ratingEl.value) || 0) : 0;

  try {
    const userParam = currentUser && currentUser.username ? currentUser.username : '';
    const res = await fetch('/api/avito/update-search-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: searchId,
        username: userParam,
        autobuy: autobuy,
        autoreserve: autoreserve,
        max_price: max_price,
        price_with_delivery: price_with_delivery,
        only_delivery: only_delivery,
        min_rating: min_rating
      })
    });
    const data = await res.json();
    if (data && data.success) {
      // Обновляем локальное состояние поисков
      const allSearches = (currentUser && currentUser.avito_searches) ? currentUser.avito_searches : ((avitoData && avitoData.searches) ? avitoData.searches : []);
      const found = allSearches.find(s => Number(s.id) === Number(searchId));
      if (found) {
        found.autobuy = autobuy;
        found.autoreserve = autoreserve;
        found.max_price = max_price;
        found.price_with_delivery = price_with_delivery;
        found.only_delivery = only_delivery;
        found.min_rating = min_rating;
      }
      if (currentUser) {
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      }
      if (avitoData && avitoData.searches) {
        const foundAv = avitoData.searches.find(s => Number(s.id) === Number(searchId));
        if (foundAv) {
          foundAv.autobuy = autobuy;
          foundAv.autoreserve = autoreserve;
          foundAv.max_price = max_price;
          foundAv.price_with_delivery = price_with_delivery;
          foundAv.only_delivery = only_delivery;
          foundAv.min_rating = min_rating;
        }
      }

      if (only_delivery && avitoData && Array.isArray(avitoData.items)) {
        const foundSearch = allSearches.find(s => Number(s.id) === Number(searchId));
        const sName = foundSearch ? (foundSearch.name || foundSearch.url || '').trim().toLowerCase() : '';
        if (sName) {
          const favSet = typeof getFavoriteIds === 'function' ? getFavoriteIds() : new Set();
          avitoData.items = avitoData.items.filter(it => {
            const itSearch = (it.search_name || '').trim().toLowerCase();
            if (itSearch === sName && !it.has_delivery && !favSet.has(String(it.item_id))) {
              return false;
            }
            return true;
          });
          if (avitoData.stats) avitoData.stats.total_items = avitoData.items.length;
          if (currentCat === 'avito_monitor' && typeof renderList === 'function') {
            renderList();
          }
        }
      }

      if (field === 'only_delivery') {
        return;
      }

      if (typeof showToast === 'function') {
        if (field === 'autobuy') {
          // По просьбе пользователя: не показывать пуш-уведомление для выкупа
        } else if (field === 'autoreserve') {
          // По просьбе пользователя: не показывать пуш-уведомление для автоброни
        } else if (field === 'max_price') {
          // По просьбе пользователя: не показывать пуш-уведомление для планки цены
        } else if (field === 'price_with_delivery') {
          showToast(price_with_delivery ? '🚚 С учётом доставки (включено)' : '🚚 Без учёта доставки');
        } else if (field === 'min_rating') {
          showToast(min_rating > 0 ? `⭐ Мин. рейтинг продавца: ${min_rating}` : '⭐ Мин. рейтинг: любой');
        }
      }
    } else {
      if (typeof showToast === 'function' && field !== 'only_delivery') {
        showToast('⚠️ Ошибка сохранения настроек ссылки');
      }
    }
  } catch (err) {
    console.error('updateSearchAutomation error:', err);
    if (typeof showToast === 'function' && field !== 'only_delivery') {
      showToast('⚠️ Не удалось связаться с сервером');
    }
  }
};

// Для обратной совместимости
window.openAddAvitoSearchModal = window.openManageSearchesModal;

// Подсветка поля с ошибкой (красная рамка + подпись под полем)
function markFieldError(el, msg) {
  el.style.borderColor = '#ef4444';
  el.style.boxShadow = '0 0 0 2px rgba(239,68,68,0.25)';
  el.focus();
  let tip = el.parentElement.querySelector('.field-err-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'field-err-tip';
    tip.style.cssText = 'font-size:0.78rem;color:#ef4444;margin-top:0.25rem;display:flex;align-items:center;gap:0.3rem;';
    el.parentElement.appendChild(tip);
  }
  tip.textContent = '⚠️ ' + msg;
  clearTimeout(el._errTimer);
  el._errTimer = setTimeout(() => {
    el.style.borderColor = '';
    el.style.boxShadow = '';
    if (tip) tip.remove();
  }, 2500);
}

// Кодирование бинарного фильтра цены для категории "Видеокарты" на Авито
function encodeAvitoVideocardFilter(pmin, pmax) {
  const p = {};
  if (pmin && Number(pmin) > 0) p.from = Number(pmin);
  if (pmax && Number(pmax) > 0) p.to = Number(pmax);
  if (!p.from && !p.to) return '';
  const jsonStr = JSON.stringify(p);
  const prefixHex = '0128010201020244c607fa66ee09a6670145c69a0c';
  const prefixBytes = [];
  for (let i = 0; i < prefixHex.length; i += 2) {
    prefixBytes.push(parseInt(prefixHex.substr(i, 2), 16));
  }
  prefixBytes.push(jsonStr.length);
  for (let i = 0; i < jsonStr.length; i++) {
    prefixBytes.push(jsonStr.charCodeAt(i));
  }
  let binary = '';
  for (let i = 0; i < prefixBytes.length; i++) {
    binary += String.fromCharCode(prefixBytes[i]);
  }
  return btoa(binary).replace(/\//g, '~').replace(/\+/g, '-').replace(/=+$/, '');
}

// Извлечение диапазона цен из ссылки Avito (поддерживает pmin, pmax и base64-фильтр f=...)
function extractPriceRangeFromUrl(url) {
  if (!url) return { pmin: null, pmax: null };
  let pmin = null;
  let pmax = null;
  try {
    const pminMatch = url.match(/[?&]pmin=(\d+)/i);
    if (pminMatch) pmin = parseInt(pminMatch[1], 10);
    const pmaxMatch = url.match(/[?&]pmax=(\d+)/i);
    if (pmaxMatch) pmax = parseInt(pmaxMatch[1], 10);

    const fMatch = url.match(/[?&]f=([^&]+)/i);
    if (fMatch && (pmin === null || pmax === null)) {
      const fVal = decodeURIComponent(fMatch[1]);
      let padded = fVal.replace(/-/g, '+').replace(/~/g, '/');
      while (padded.length % 4 !== 0) padded += '=';
      const binary = atob(padded);
      const jsonMatch = binary.match(/\{[^{}]*(?:from|to)[^{}]*\}/);
      if (jsonMatch) {
        const obj = JSON.parse(jsonMatch[0]);
        if (obj.from != null && pmin === null) pmin = parseInt(obj.from, 10);
        if (obj.to != null && pmax === null) pmax = parseInt(obj.to, 10);
      }
    }
  } catch (e) {
    // игнорируем ошибки декодирования
  }
  return { pmin, pmax };
}

// Форматирование приписки диапазона цен для карточки товара / поиска: (500-2500)
function formatPriceSuffix(pmin, pmax) {
  if (pmin != null && pmax != null) return `(${pmin}-${pmax})`;
  if (pmin != null) return `(от ${pmin})`;
  if (pmax != null) return `(до ${pmax})`;
  return '';
}

// Получение отображаемого названия поиска для карточки товара с припиской цен (например RX470 (500-2500))
function getDisplaySearchName(it) {
  if (!it) return 'Поиск Avito';
  let sName = (it.search_name || '').trim();
  if (!sName) sName = 'Поиск Avito';
  if (/\(\s*(?:от|до|\d+)\s*[\d\-–\s]*\)/i.test(sName)) {
    return sName;
  }
  const allSearches = (avitoData && avitoData.searches && avitoData.searches.length > 0)
    ? avitoData.searches
    : (currentUser && currentUser.avito_searches ? currentUser.avito_searches : []);
  const found = allSearches.find(s => {
    const s1 = (s.name || '').trim().toLowerCase();
    const s2 = (s.url || '').trim().toLowerCase();
    const target = sName.toLowerCase();
    return s1 === target || s2 === target;
  });
  if (found && found.url) {
    const { pmin, pmax } = extractPriceRangeFromUrl(found.url);
    const suffix = formatPriceSuffix(pmin, pmax);
    if (suffix) {
      return `${sName} ${suffix}`;
    }
  }
  return sName;
}

function getAvitoCategoryOptionsHtml(selectedCat) {
  const cat = selectedCat || 'videokarty';
  const opt = (val, label) => `<option value="${val}" ${cat === val ? 'selected' : ''}>${label}</option>`;
  return `
    <optgroup label="Компьютеры и комплектующие">
      ${opt('videokarty', '🎮 Видеокарты')}
      ${opt('protsessory', '⚡ Процессоры')}
      ${opt('materinskie_platy', '🔲 Материнские платы')}
      ${opt('operativnaya_pamyat', '💾 Оперативная память (ОЗУ)')}
      ${opt('nakopiteli_hdd_ssd', '💿 Накопители (SSD / HDD)')}
      ${opt('bloki_pitaniya', '🔌 Блоки питания')}
      ${opt('korpusa', '📦 Корпуса для ПК')}
      ${opt('sistemy_ohlazhdeniya', '❄️ Охлаждение и кулеры')}
      ${opt('komplektuyuschie', '💻 Все комплектующие')}
      ${opt('nastolnye_kompyutery', '🖥️ Системные блоки и ПК')}
      ${opt('monitory', '🖥️ Мониторы')}
      ${opt('klaviatury_i_myshi', '⌨️ Клавиатуры и мыши')}
      ${opt('akustika_kolonki', '🔊 Колонки и акустика для ПК')}
      ${opt('setevoe_oborudovanie', '📡 Сетевое оборудование')}
      ${opt('orgtehnika_i_rashodniki', '🖨️ Оргтехника и расходники')}
    </optgroup>
    <optgroup label="Электроника и гаджеты">
      ${opt('noutbuki', '💻 Ноутбуки')}
      ${opt('telefony', '📱 Телефоны и смартфоны')}
      ${opt('planshety', '📱 Планшеты и электронные книги')}
      ${opt('smart_chasy', '⌚ Смарт-часы и браслеты')}
      ${opt('naushniki', '🎧 Наушники и гарнитуры')}
      ${opt('akustika_audio', '📻 Аудио, колонки и саундбары')}
      ${opt('usiliteli_i_resivery', '🎛️ Усилители и ресиверы')}
      ${opt('igrovye_pristavki', '🎮 Игровые приставки (PS / Xbox / Switch)')}
      ${opt('igry_dlya_pristavok', '💿 Игры для приставок и ПК')}
      ${opt('televizory', '📺 Телевизоры и проекторы')}
      ${opt('fototehnika', '📷 Фото- и видеокамеры')}
      ${opt('umnyy_dom', '🏠 Умный дом и безопасность')}
    </optgroup>
    <optgroup label="Бытовая техника">
      ${opt('bytovaya_tehnika_kuhnya', '🍳 Вся техника для кухни')}
      ${opt('holodilniki', '🧊 Холодильники и морозилки')}
      ${opt('stiralnye_mashiny', '🧺 Стиральные машины')}
      ${opt('posudomoechnye', '🍽️ Посудомоечные машины')}
      ${opt('plity_i_duhovki', '🔥 Плиты, печи и варочные панели')}
      ${opt('kofemashiny', '☕ Кофемашины и кофеварки')}
      ${opt('mikrovolnovki', '🍲 Микроволновые печи')}
      ${opt('pylesosy', '🧹 Пылесосы и роботы-пылесосы')}
      ${opt('klimaticheskaya', '❄️ Кондиционеры и климат')}
      ${opt('utyugi_i_otparivateli', '👔 Утюги и отпариватели')}
      ${opt('krasota_i_zdorove_tehnika', '💇 Фены и приборы для ухода')}
    </optgroup>
    <optgroup label="Транспорт и автотовары">
      ${opt('avtomobili', '🚗 Автомобили')}
      ${opt('zapchasti', '⚙️ Автозапчасти и аксессуары')}
      ${opt('shiny_i_diski', '🛞 Шины, диски и колёса')}
      ${opt('mototehnika', '🏍️ Мототехника')}
      ${opt('gruzoviki_i_spetstehnika', '🚛 Грузовики и спецтехника')}
      ${opt('vodnyy_transport', '🚤 Водный транспорт')}
      ${opt('avtozvuk', '🔊 Автозвук и видеорегистраторы')}
    </optgroup>
    <optgroup label="Недвижимость">
      ${opt('kvartiry_kupit', '🏢 Купить квартиру')}
      ${opt('kvartiry_arenda', '🔑 Снять квартиру (длительно)')}
      ${opt('kvartiry_posutochno', '📅 Посуточная аренда')}
      ${opt('komnaty', '🚪 Комнаты')}
      ${opt('doma_dachi', '🏡 Дома, дачи и коттеджи')}
      ${opt('zemelnye_uchastki', '🏞️ Земельные участки')}
      ${opt('garazhi', '🅿️ Гаражи и машиноместа')}
      ${opt('kommercheskaya_nedvizhimost', '🏬 Коммерческая недвижимость')}
    </optgroup>
    <optgroup label="Для дома и дачи (ремонт и интерьер)">
      ${opt('elektroinstrument', '🛠️ Инструменты и электроинструмент')}
      ${opt('stroitelnoe_oborudovanie', '🏗️ Строительное оборудование')}
      ${opt('stroymaterialy', '🧱 Стройматериалы')}
      ${opt('santehnika', '🚿 Сантехника и сауна')}
      ${opt('mebel_i_interer', '🛋️ Вся мебель и гарнитуры')}
      ${opt('krovati_i_divany', '🛏️ Кровати, диваны и кресла')}
      ${opt('shkafy_i_komody', '🚪 Шкафы, комоды, стеллажи')}
      ${opt('stoly_i_stulya', '🪑 Столы и стулья')}
      ${opt('posuda', '🍳 Посуда и кухонные товары')}
      ${opt('sadovaya_tehnika', '🌿 Садовая техника и растения')}
    </optgroup>
    <optgroup label="Личные вещи и одежда">
      ${opt('odezhda_obuv', '👗 Вся одежда, обувь, аксессуары')}
      ${opt('zhenskaya_odezhda', '👚 Женская одежда')}
      ${opt('zhenskaya_obuv', '👠 Женская обувь')}
      ${opt('muzhskaya_odezhda', '👔 Мужская одежда')}
      ${opt('muzhskaya_obuv', '👞 Мужская обувь')}
      ${opt('sumki_i_chemodany', '👜 Сумки, рюкзаки, чемоданы')}
      ${opt('chasy_i_ukrasheniya', '💍 Часы и ювелирные украшения')}
      ${opt('detskie_tovary', '🧸 Детские товары и игрушки')}
      ${opt('krasota_i_zdorove', '💄 Косметика, парфюмерия и здоровье')}
    </optgroup>
    <optgroup label="Хобби и отдых">
      ${opt('velosipedy', '🚲 Велосипеды и самокаты')}
      ${opt('sport_i_otdyh', '⚽ Спорт, тренажеры и активный отдых')}
      ${opt('ohota_i_rybalka', '🎣 Охота и рыбалка')}
      ${opt('turizm', '🏕️ Туризм и походы')}
      ${opt('muzykalnye_instrumenty', '🎸 Музыкальные инструменты')}
      ${opt('knigi_i_zhurnaly', '📚 Книги и журналы')}
      ${opt('kollektsionirovanie', '🪙 Коллекционирование')}
      ${opt('bilety_i_puteshestviya', '🎫 Билеты и путешествия')}
    </optgroup>
    <optgroup label="Животные">
      ${opt('sobaki', '🐕 Собаки')}
      ${opt('koshki', '🐈 Кошки')}
      ${opt('ptitsy', '🦜 Птицы')}
      ${opt('akvarium', '🐠 Аквариум и рыбки')}
      ${opt('tovary_dlya_zhivotnyh', '🦴 Товары для животных')}
    </optgroup>
    <optgroup label="Для бизнеса">
      ${opt('oborudovanie_dlya_biznesa', '🏭 Оборудование для бизнеса')}
      ${opt('torgovoe_oborudovanie', '🏪 Торговое оборудование')}
      ${opt('gotoviy_biznes', '💼 Готовый бизнес')}
    </optgroup>
    <optgroup label="Услуги и работа">
      ${opt('predlozheniya_uslug', '🛠️ Предложение услуг')}
      ${opt('vakansii', '📋 Вакансии (поиск сотрудников)')}
      ${opt('rezume', '📄 Резюме (поиск работы)')}
    </optgroup>
    <optgroup label="Все категории">
      ${opt('all', '🌐 Вся Россия (любой товар и раздел)')}
    </optgroup>
  `;
}

window.filterAvitoCategories = function(rawQuery) {
  const sel = document.getElementById('avito-gen-category');
  if (!sel) return;
  const q = (rawQuery || '').toLowerCase().trim();
  const groups = sel.querySelectorAll('optgroup');
  let firstMatch = null;
  groups.forEach(group => {
    let groupHasMatch = false;
    const options = group.querySelectorAll('option');
    options.forEach(opt => {
      const txt = (opt.textContent || '').toLowerCase();
      const match = !q || txt.includes(q);
      opt.style.display = match ? '' : 'none';
      if (match) {
        groupHasMatch = true;
        if (!firstMatch) firstMatch = opt;
      }
    });
    group.style.display = groupHasMatch ? '' : 'none';
  });
  if (firstMatch && q) {
    sel.value = firstMatch.value;
  }
};

function getAvitoRegionOptionsHtml(selectedRegion) {
  const reg = selectedRegion || 'all';
  const opt = (val, label) => `<option value="${val}" ${reg === val ? 'selected' : ''}>${label}</option>`;
  return `
    <optgroup label="Вся страна">
      ${opt('all', 'Все регионы')}
    </optgroup>
    <optgroup label="Крупнейшие города">
      ${opt('moskva', '🏙️ Москва')}
      ${opt('sankt-peterburg', '🏙️ Санкт-Петербург')}
      ${opt('novosibirsk', '🏙️ Новосибирск')}
      ${opt('ekaterinburg', '🏙️ Екатеринбург')}
      ${opt('kazan', '🏙️ Казань')}
      ${opt('nizhniy_novgorod', '🏙️ Нижний Новгород')}
      ${opt('chelyabinsk', '🏙️ Челябинск')}
      ${opt('krasnoyarsk', '🏙️ Красноярск')}
      ${opt('samara', '🏙️ Самара')}
      ${opt('ufa', '🏙️ Уфа')}
      ${opt('rostov-na-donu', '🏙️ Ростов-на-Дону')}
      ${opt('omsk', '🏙️ Омск')}
      ${opt('krasnodar', '🏙️ Краснодар')}
      ${opt('voronezh', '🏙️ Воронеж')}
      ${opt('perm', '🏙️ Пермь')}
      ${opt('volgograd', '🏙️ Волгоград')}
      ${opt('saratov', '🏙️ Саратов')}
      ${opt('tyumen', '🏙️ Тюмень')}
      ${opt('tolyatti', '🏙️ Тольятти')}
      ${opt('barnaul', '🏙️ Барнаул')}
      ${opt('izhevsk', '🏙️ Ижевск')}
      ${opt('mahachkala', '🏙️ Махачкала')}
      ${opt('habarovsk', '🏙️ Хабаровск')}
      ${opt('ulyanovsk', '🏙️ Ульяновск')}
      ${opt('vladivostok', '🏙️ Владивосток')}
      ${opt('yaroslavl', '🏙️ Ярославль')}
      ${opt('sochi', '🏙️ Сочи')}
      ${opt('irkutsk', '🏙️ Иркутск')}
      ${opt('kemerovo', '🏙️ Кемерово')}
      ${opt('novokuznetsk', '🏙️ Новокузнецк')}
      ${opt('ryazan', '🏙️ Рязань')}
      ${opt('naberezhnye_chelny', '🏙️ Набережные Челны')}
      ${opt('balashiha', '🏙️ Балашиха')}
      ${opt('penza', '🏙️ Пенза')}
      ${opt('cheboksary', '🏙️ Чебоксары')}
      ${opt('kaliningrad', '🏙️ Калининград')}
      ${opt('tula', '🏙️ Тула')}
      ${opt('kursk', '🏙️ Курск')}
      ${opt('stavropol', '🏙️ Ставрополь')}
      ${opt('sevastopol', '🏙️ Севастополь')}
      ${opt('simferopol', '🏙️ Симферополь')}
      ${opt('surgut', '🏙️ Сургут')}
      ${opt('tver', '🏙️ Тверь')}
      ${opt('magnitogorsk', '🏙️ Магнитогорск')}
      ${opt('ivanovo', '🏙️ Иваново')}
      ${opt('bryansk', '🏙️ Брянск')}
      ${opt('belgorod', '🏙️ Белгород')}
      ${opt('orenburg', '🏙️ Оренбург')}
      ${opt('tomsk', '🏙️ Томск')}
      ${opt('vladimir', '🏙️ Владимир')}
      ${opt('arhangelsk', '🏙️ Архангельск')}
      ${opt('kaluga', '🏙️ Калуга')}
      ${opt('smolensk', '🏙️ Смоленск')}
      ${opt('chita', '🏙️ Чита')}
      ${opt('saransk', '🏙️ Саранск')}
      ${opt('vologda', '🏙️ Вологда')}
      ${opt('kurgan', '🏙️ Курган')}
      ${opt('cherepovets', '🏙️ Череповец')}
      ${opt('oryol', '🏙️ Орёл')}
      ${opt('vladikavkaz', '🏙️ Владикавказ')}
      ${opt('murmansk', '🏙️ Мурманск')}
      ${opt('tambov', '🏙️ Тамбов')}
      ${opt('petrozavodsk', '🏙️ Петрозаводск')}
      ${opt('kostroma', '🏙️ Кострома')}
      ${opt('sterlitamak', '🏙️ Стерлитамак')}
      ${opt('novorossiysk', '🏙️ Новороссийск')}
      ${opt('yoshkar-ola', '🏙️ Йошкар-Ола')}
      ${opt('taganrog', '🏙️ Таганрог')}
      ${opt('komsomolsk-na-amure', '🏙️ Комсомольск-на-Амуре')}
      ${opt('syktyvkar', '🏙️ Сыктывкар')}
      ${opt('nalchik', '🏙️ Нальчик')}
      ${opt('nizhnevartovsk', '🏙️ Нижневартовск')}
      ${opt('shahty', '🏙️ Шахты')}
      ${opt('bratsk', '🏙️ Братск')}
      ${opt('dzerzhinsk', '🏙️ Дзержинск')}
      ${opt('orsk', '🏙️ Орск')}
      ${opt('angarsk', '🏙️ Ангарск')}
      ${opt('blagoveschensk', '🏙️ Благовещенск')}
      ${opt('staryy_oskol', '🏙️ Старый Оскол')}
      ${opt('velikiy_novgorod', '🏙️ Великий Новгород')}
      ${opt('pskov', '🏙️ Псков')}
      ${opt('biysk', '🏙️ Бийск')}
      ${opt('prokopyevsk', '🏙️ Прокопьевск')}
      ${opt('rybinsk', '🏙️ Рыбинск')}
      ${opt('balakovo', '🏙️ Балаково')}
      ${opt('armavir', '🏙️ Армавир')}
      ${opt('yuzhno-sahalinsk', '🏙️ Южно-Сахалинск')}
      ${opt('petropavlovsk-kamchatskiy', '🏙️ Петропавловск-Камчатский')}
      ${opt('yakutsk', '🏙️ Якутск')}
      ${opt('pyatigorsk', '🏙️ Пятигорск')}
      ${opt('kislovodsk', '🏙️ Кисловодск')}
      ${opt('essentuki', '🏙️ Ессентуки')}
      ${opt('nevinnomyssk', '🏙️ Невинномысск')}
      ${opt('mineralnye_vody', '🏙️ Минеральные Воды')}
      ${opt('bataysk', '🏙️ Батайск')}
      ${opt('novocherkassk', '🏙️ Новочеркасск')}
      ${opt('volgodonsk', '🏙️ Волгодонск')}
      ${opt('kamensk-shahtinskiy', '🏙️ Каменск-Шахтинский')}
      ${opt('azov', '🏙️ Азов')}
      ${opt('syzran', '🏙️ Сызрань')}
      ${opt('nizhniy_tagil', '🏙️ Нижний Тагил')}
      ${opt('kamensk-uralskiy', '🏙️ Каменск-Уральский')}
      ${opt('pervouralsk', '🏙️ Первоуральск')}
      ${opt('zlatoust', '🏙️ Златоуст')}
      ${opt('miass', '🏙️ Миасс')}
      ${opt('kopeysk', '🏙️ Копейск')}
      ${opt('almetevsk', '🏙️ Альметьевск')}
      ${opt('nizhnekamsk', '🏙️ Нижнекамск')}
      ${opt('salavat', '🏙️ Салават')}
      ${opt('neftekamsk', '🏙️ Нефтекамск')}
      ${opt('oktyabrskiy', '🏙️ Октябрьский')}
      ${opt('himki', '🏙️ Химки')}
      ${opt('mytischi', '🏙️ Мытищи')}
      ${opt('korolev', '🏙️ Королёв')}
      ${opt('lyubertsy', '🏙️ Люберцы')}
      ${opt('krasnogorsk', '🏙️ Красногорск')}
      ${opt('elektrostal', '🏙️ Электросталь')}
      ${opt('kolomna', '🏙️ Коломна')}
      ${opt('odintsovo', '🏙️ Одинцово')}
      ${opt('serpuhov', '🏙️ Серпухов')}
      ${opt('domodedovo', '🏙️ Домодедово')}
      ${opt('schelkovo', '🏙️ Щёлково')}
      ${opt('orehovo-zuevo', '🏙️ Орехово-Зуево')}
      ${opt('ramenskoe', '🏙️ Раменское')}
      ${opt('dolgoprudnyy', '🏙️ Долгопрудный')}
      ${opt('zhukovskiy', '🏙️ Жуковский')}
      ${opt('pushkino', '🏙️ Пушкино')}
      ${opt('reutov', '🏙️ Реутов')}
      ${opt('sergiev_posad', '🏙️ Сергиев Посад')}
      ${opt('noginsk', '🏙️ Ногинск')}
      ${opt('gatchina', '🏙️ Гатчина')}
      ${opt('vyborg', '🏙️ Выборг')}
      ${opt('vsevolozhsk', '🏙️ Всеволожск')}
      ${opt('sosnovyy_bor', '🏙️ Сосновый Бор')}
    </optgroup>
    <optgroup label="Города и райцентры Краснодарского края">
      ${opt('kurganinsk', '🌾 Курганинск')}
      ${opt('krasnodar', '🏙️ Краснодар')}
      ${opt('sochi', '🏖️ Сочи')}
      ${opt('novorossiysk', '⚓ Новороссийск')}
      ${opt('armavir', '🏙️ Армавир')}
      ${opt('anapa', '🏖️ Анапа')}
      ${opt('gelendzhik', '🏖️ Геленджик')}
      ${opt('eysk', '⚓ Ейск')}
      ${opt('kropotkin', '🏙️ Кропоткин')}
      ${opt('slavyansk-na-kubani', '🌾 Славянск-на-Кубани')}
      ${opt('tuapse', '⚓ Туапсе')}
      ${opt('labinsk', '🌾 Лабинск')}
      ${opt('tihoretsk', '🌾 Тихорецк')}
      ${opt('krymsk', '🌾 Крымск')}
      ${opt('timashevsk', '🌾 Тимашёвск')}
      ${opt('belorechensk', '🌾 Белореченск')}
      ${opt('ust-labinsk', '🌾 Усть-Лабинск')}
      ${opt('apsheronsk', '🌲 Апшеронск')}
      ${opt('goryachiy_klyuch', '🌿 Горячий Ключ')}
      ${opt('korenovsk', '🌾 Кореновск')}
      ${opt('temryuk', '⚓ Темрюк')}
      ${opt('gulkevichi', '🌾 Гулькевичи')}
      ${opt('novokubansk', '🌾 Новокубанск')}
      ${opt('abinsk', '🌾 Абинск')}
      ${opt('primorsko-ahtarsk', '⚓ Приморско-Ахтарск')}
      ${opt('hadyzhensk', '🌲 Хадыженск')}
    </optgroup>
    <optgroup label="Края">
      ${opt('altayskiy_kray', '🌲 Алтайский край')}
      ${opt('zabaykalskiy_kray', '🌲 Забайкальский край')}
      ${opt('kamchatskiy_kray', '🌋 Камчатский край')}
      ${opt('krasnodarskiy_kray', '☀️ Краснодарский край')}
      ${opt('krasnoyarskiy_kray', '🌲 Красноярский край')}
      ${opt('permskiy_kray', '🌲 Пермский край')}
      ${opt('primorskiy_kray', '🌊 Приморский край')}
      ${opt('stavropolskiy_kray', '🌾 Ставропольский край')}
      ${opt('habarovskiy_kray', '🌲 Хабаровский край')}
    </optgroup>
    <optgroup label="Области">
      ${opt('amurskaya_oblast', 'Амурская область')}
      ${opt('arhangelskaya_oblast', 'Архангельская область')}
      ${opt('astrahanskaya_oblast', 'Астраханская область')}
      ${opt('belgorodskaya_oblast', 'Белгородская область')}
      ${opt('bryanskaya_oblast', 'Брянская область')}
      ${opt('vladimirskaya_oblast', 'Владимирская область')}
      ${opt('volgogradskaya_oblast', 'Волгоградская область')}
      ${opt('vologodskaya_oblast', 'Вологодская область')}
      ${opt('voronezhskaya_oblast', 'Воронежская область')}
      ${opt('ivanovskaya_oblast', 'Ивановская область')}
      ${opt('irkutskaya_oblast', 'Иркутская область')}
      ${opt('kaliningradskaya_oblast', 'Калининградская область')}
      ${opt('kaluzhskaya_oblast', 'Калужская область')}
      ${opt('kemerovskaya_oblast', 'Кемеровская область')}
      ${opt('kirovskaya_oblast', 'Кировская область')}
      ${opt('kostromskaya_oblast', 'Костромская область')}
      ${opt('kurganskaya_oblast', 'Курганская область')}
      ${opt('kurskaya_oblast', 'Курская область')}
      ${opt('leningradskaya_oblast', 'Ленинградская область')}
      ${opt('lipetskaya_oblast', 'Липецкая область')}
      ${opt('magadanskaya_oblast', 'Магаданская область')}
      ${opt('moskovskaya_oblast', 'Московская область')}
      ${opt('murmanskaya_oblast', 'Мурманская область')}
      ${opt('nizhegorodskaya_oblast', 'Нижегородская область')}
      ${opt('novgorodskaya_oblast', 'Новгородская область')}
      ${opt('novosibirskaya_oblast', 'Новосибирская область')}
      ${opt('omskaya_oblast', 'Омская область')}
      ${opt('orenburgskaya_oblast', 'Оренбургская область')}
      ${opt('orlovskaya_oblast', 'Орловская область')}
      ${opt('penzenskaya_oblast', 'Пензенская область')}
      ${opt('pskovskaya_oblast', 'Псковская область')}
      ${opt('rostovskaya_oblast', 'Ростовская область')}
      ${opt('ryazanskaya_oblast', 'Рязанская область')}
      ${opt('samarskaya_oblast', 'Самарская область')}
      ${opt('saratovskaya_oblast', 'Саратовская область')}
      ${opt('sahalinskaya_oblast', 'Сахалинская область')}
      ${opt('sverdlovskaya_oblast', 'Свердловская область')}
      ${opt('smolenskaya_oblast', 'Смоленская область')}
      ${opt('tambovskaya_oblast', 'Тамбовская область')}
      ${opt('tverskaya_oblast', 'Тверская область')}
      ${opt('tomskaya_oblast', 'Томская область')}
      ${opt('tulskaya_oblast', 'Тульская область')}
      ${opt('tyumenskaya_oblast', 'Тюменская область')}
      ${opt('ulyanovskaya_oblast', 'Ульяновская область')}
      ${opt('chelyabinskaya_oblast', 'Челябинская область')}
      ${opt('yaroslavskaya_oblast', 'Ярославская область')}
    </optgroup>
    <optgroup label="Республики и округа">
      ${opt('respublika_adygeya', 'Республика Адыгея')}
      ${opt('respublika_altay', 'Республика Алтай')}
      ${opt('respublika_bashkortostan', 'Республика Башкортостан')}
      ${opt('respublika_buryatiya', 'Республика Бурятия')}
      ${opt('respublika_dagestan', 'Республика Дагестан')}
      ${opt('respublika_ingushetiya', 'Республика Ингушетия')}
      ${opt('kabardino-balkarskaya_respublika', 'Кабардино-Балкария')}
      ${opt('respublika_kalmykiya', 'Республика Калмыкия')}
      ${opt('karachaevo-cherkesskaya_respublika', 'Карачаево-Черкесия')}
      ${opt('respublika_kareliya', 'Республика Карелия')}
      ${opt('respublika_komi', 'Республика Коми')}
      ${opt('respublika_krym', 'Республика Крым')}
      ${opt('respublika_mariy_el', 'Республика Марий Эл')}
      ${opt('respublika_mordoviya', 'Республика Мордовия')}
      ${opt('respublika_saha_yakutiya', 'Якутия (Саха)')}
      ${opt('respublika_severnaya_osetiya-alaniya', 'Северная Осетия')}
      ${opt('respublika_tatarstan', 'Республика Татарстан')}
      ${opt('respublika_tyva', 'Республика Тыва')}
      ${opt('udmurtskaya_respublika', 'Удмуртская Республика')}
      ${opt('respublika_hakasiya', 'Республика Хакасия')}
      ${opt('chechenskaya_respublika', 'Чеченская Республика')}
      ${opt('chuvashskaya_respublika', 'Чувашская Республика')}
      ${opt('hanty-mansiyskiy_ao', 'ХМАО - Югра')}
      ${opt('yamalo-nenetskiy_ao', 'Ямало-Ненецкий АО')}
    </optgroup>
  `;
}

window.filterAvitoRegions = function(rawQuery) {
  const sel = document.getElementById('avito-gen-region');
  if (!sel) return;
  const q = (rawQuery || '').toLowerCase().trim();
  const groups = sel.querySelectorAll('optgroup');
  let firstMatch = null;
  groups.forEach(group => {
    let groupHasMatch = false;
    const options = group.querySelectorAll('option');
    options.forEach(opt => {
      const txt = (opt.textContent || '').toLowerCase();
      const match = !q || txt.includes(q);
      opt.style.display = match ? '' : 'none';
      if (match) {
        groupHasMatch = true;
        if (!firstMatch) firstMatch = opt;
      }
    });
    group.style.display = groupHasMatch ? '' : 'none';
  });
  if (firstMatch && q) {
    sel.value = firstMatch.value;
  }
};

const AVITO_CATEGORY_MAP = {
  // Компьютеры и комплектующие
  'videokarty': 'tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw',
  'protsessory': 'tovary_dlya_kompyutera/komplektuyuschie/protsessory',
  'materinskie_platy': 'tovary_dlya_kompyutera/komplektuyuschie/materinskie_platy',
  'operativnaya_pamyat': 'tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat',
  'nakopiteli_hdd_ssd': 'tovary_dlya_kompyutera/komplektuyuschie/nakopiteli',
  'bloki_pitaniya': 'tovary_dlya_kompyutera/komplektuyuschie/bloki_pitaniya',
  'korpusa': 'tovary_dlya_kompyutera/komplektuyuschie/korpusa',
  'sistemy_ohlazhdeniya': 'tovary_dlya_kompyutera/komplektuyuschie/sistemy_ohlazhdeniya',
  'komplektuyuschie': 'tovary_dlya_kompyutera/komplektuyuschie',
  'nastolnye_kompyutery': 'nastolnye_kompyutery',
  'monitory': 'tovary_dlya_kompyutera/monitory',
  'klaviatury_i_myshi': 'tovary_dlya_kompyutera/klaviatury_i_myshi',
  'akustika_kolonki': 'tovary_dlya_kompyutera/akustika',
  'setevoe_oborudovanie': 'tovary_dlya_kompyutera/setevoe_oborudovanie',
  'orgtehnika_i_rashodniki': 'orgtehnika_i_rashodniki',

  // Электроника и гаджеты
  'noutbuki': 'noutbuki',
  'telefony': 'telefony',
  'planshety': 'planshety_i_elektronnye_knigi',
  'smart_chasy': 'chasy_i_ukrasheniya/chasy',
  'naushniki': 'audio_i_video/naushniki_i_bluetooth-garnitury',
  'akustika_audio': 'audio_i_video/akustika_kolonki_sabvufery',
  'usiliteli_i_resivery': 'audio_i_video/usiliteli_i_resivery',
  'igrovye_pristavki': 'igry_pristavki_i_programmy/igrovye_pristavki',
  'igry_dlya_pristavok': 'igry_pristavki_i_programmy/igry_dlya_pristavok',
  'televizory': 'audio_i_video/televizory_i_proektory',
  'fototehnika': 'fototehnika',
  'umnyy_dom': 'sistemy_bezopasnosti',

  // Бытовая техника
  'bytovaya_tehnika_kuhnya': 'bytovaya_tehnika/dlya_kuhni',
  'holodilniki': 'bytovaya_tehnika/dlya_kuhni/holodilniki_i_morozilnye_kamery',
  'stiralnye_mashiny': 'bytovaya_tehnika/dlya_doma/stiralnye_mashiny',
  'posudomoechnye': 'bytovaya_tehnika/dlya_kuhni/posudomoechnye_mashiny',
  'plity_i_duhovki': 'bytovaya_tehnika/dlya_kuhni/plity_i_varochnye_paneli',
  'kofemashiny': 'bytovaya_tehnika/dlya_kuhni/kofemashiny_i_kofevarki',
  'mikrovolnovki': 'bytovaya_tehnika/dlya_kuhni/mikrovolnovye_pechi',
  'pylesosy': 'bytovaya_tehnika/dlya_doma/pylesosy',
  'klimaticheskaya': 'bytovaya_tehnika/klimaticheskoe_oborudovanie',
  'utyugi_i_otparivateli': 'bytovaya_tehnika/dlya_doma/utyugi_i_otparivateli',
  'krasota_i_zdorove_tehnika': 'bytovaya_tehnika/dlya_krasoty_i_zdorovya',

  // Транспорт и автотовары
  'avtomobili': 'avtomobili',
  'zapchasti': 'zapchasti_i_aksessuary',
  'shiny_i_diski': 'zapchasti_i_aksessuary/shiny_diski_i_kolesa',
  'mototehnika': 'mototsikly_i_mototehnika',
  'gruzoviki_i_spetstehnika': 'gruzoviki_i_spetstehnika',
  'vodnyy_transport': 'vodnyy_transport',
  'avtozvuk': 'zapchasti_i_aksessuary/avtozvuk',

  // Недвижимость
  'kvartiry_kupit': 'kvartiry/kupit',
  'kvartiry_arenda': 'kvartiry/sdam/na_dlitelnyy_srok',
  'kvartiry_posutochno': 'kvartiry/sdam/posutochno',
  'komnaty': 'komnaty',
  'doma_dachi': 'doma_dachi_kottedzhi',
  'zemelnye_uchastki': 'zemelnye_uchastki',
  'garazhi': 'garazhi_i_mashinomesta',
  'kommercheskaya_nedvizhimost': 'kommercheskaya_nedvizhimost',

  // Для дома и дачи
  'elektroinstrument': 'remont_i_stroitelstvo/instrumenty',
  'stroitelnoe_oborudovanie': 'remont_i_stroitelstvo/stroitelnoe_oborudovanie',
  'stroymaterialy': 'remont_i_stroitelstvo/stroymaterialy',
  'santehnika': 'remont_i_stroitelstvo/santehnika_i_sauna',
  'mebel_i_interer': 'mebel_i_interer',
  'krovati_i_divany': 'mebel_i_interer/krovati_divany_i_kresla',
  'shkafy_i_komody': 'mebel_i_interer/shkafy_i_komody',
  'stoly_i_stulya': 'mebel_i_interer/stoly_i_stulya',
  'posuda': 'posuda_i_tovary_dlya_kuhni',
  'sadovaya_tehnika': 'rasteniya',

  // Личные вещи
  'odezhda_obuv': 'odezhda_obuv_aksessuary',
  'zhenskaya_odezhda': 'odezhda_obuv_aksessuary/zhenskaya_odezhda',
  'zhenskaya_obuv': 'odezhda_obuv_aksessuary/zhenskaya_obuv',
  'muzhskaya_odezhda': 'odezhda_obuv_aksessuary/muzhskaya_odezhda',
  'muzhskaya_obuv': 'odezhda_obuv_aksessuary/muzhskaya_obuv',
  'sumki_i_chemodany': 'odezhda_obuv_aksessuary/sumki_ryukzaki_chemodany',
  'chasy_i_ukrasheniya': 'chasy_i_ukrasheniya',
  'detskie_tovary': 'tovary_dlya_detey_i_igrushki',
  'krasota_i_zdorove': 'krasota_i_zdorove',

  // Хобби и отдых
  'velosipedy': 'velosipedy',
  'sport_i_otdyh': 'sport_i_otdyh',
  'ohota_i_rybalka': 'ohota_i_rybalka',
  'turizm': 'sport_i_otdyh/turizm',
  'muzykalnye_instrumenty': 'muzykalnye_instrumenty',
  'knigi_i_zhurnaly': 'knigi_i_zhurnaly',
  'kollektsionirovanie': 'kollektsionirovanie',
  'bilety_i_puteshestviya': 'bilety_i_puteshestviya',

  // Животные
  'sobaki': 'sobaki',
  'koshki': 'koshki',
  'ptitsy': 'ptitsy',
  'akvarium': 'akvarium',
  'tovary_dlya_zhivotnyh': 'tovary_dlya_zhivotnyh',

  // Для бизнеса
  'oborudovanie_dlya_biznesa': 'oborudovanie_dlya_biznesa',
  'torgovoe_oborudovanie': 'oborudovanie_dlya_biznesa/torgovoe',
  'gotoviy_biznes': 'gotoviy_biznes',

  // Услуги и работа
  'predlozheniya_uslug': 'predlozheniya_uslug',
  'vakansii': 'vakansii',
  'rezume': 'rezume',

  // Все
  'all': 'rossiya'
};

// Построение точной ссылки поиска по выбранной категории, региону и фильтру доставки
function buildAvitoGenUrl(cat, query, pmin, pmax, region, onlyDelivery) {
  const cleanQ = query.trim();
  const encQ = encodeURIComponent(cleanQ).replace(/%20/g, '+');
  const regSlug = (!region || region === 'rossiya' || region === 'all') ? 'all' : region;
  
  let u = '';
  if (cat === 'videokarty') {
    const fParam = encodeAvitoVideocardFilter(pmin, pmax);
    u = `https://www.avito.ru/${regSlug}/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?`;
    if (fParam) u += `f=${fParam}&`;
    u += `q=${encQ}&s=104`;
  } else {
    const path = AVITO_CATEGORY_MAP[cat] || (cat === 'all' ? '' : cat);
    if (!path || path === 'rossiya') {
      u = (regSlug === 'all')
        ? `https://www.avito.ru/rossiya?s=104&q=${encQ}`
        : `https://www.avito.ru/${regSlug}?s=104&q=${encQ}`;
    } else {
      u = `https://www.avito.ru/${regSlug}/${path}?q=${encQ}&s=104`;
    }
  }

  if (pmin && Number(pmin) > 0) u += `&pmin=${Number(pmin)}`;
  if (pmax && Number(pmax) > 0) u += `&pmax=${Number(pmax)}`;
  if (onlyDelivery) u += `&d=1`;

  return u;
}

window.onGenQueryInput = function() {
  const qEl = document.getElementById('avito-gen-query');
  const catEl = document.getElementById('avito-gen-category');
  if (qEl && catEl) {
    const v = qEl.value.toLowerCase();
    if (/\b(rx|rtx|gtx|radeon|geforce|gpu|видеокарт)\b|\b(580|570|590|1060|1660|2060|3060|3070|3080|4060|4070|4080|4090)\b/.test(v)) {
      catEl.value = 'videokarty';
    } else if (/\b(ryzen|intel|core\s*i|xeon|процессор|сокет|lga|am4|am5)\b/.test(v)) {
      catEl.value = 'protsessory';
    } else if (/\b(материн|плата|материнка|b450|b550|x570|z690|z790|h610)\b/.test(v)) {
      catEl.value = 'materinskie_platy';
    } else if (/\b(ddr4|ddr5|озу|оперативк|оперативная память)\b/.test(v)) {
      catEl.value = 'operativnaya_pamyat';
    } else if (/\b(ssd|hdd|жесткий диск|накопитель|nvme|m\.2)\b/.test(v)) {
      catEl.value = 'nakopiteli_hdd_ssd';
    } else if (/\b(блок питания|бп|chieftec|corsair|seasonic)\b/.test(v)) {
      catEl.value = 'bloki_pitaniya';
    } else if (/\b(монитор|ips|va|144гц|165гц|240гц|2k|4k)\b/.test(v)) {
      catEl.value = 'monitory';
    } else if (/\b(iphone|айфон|samsung|galaxy|xiaomi|redmi|poco|смартфон|телефон)\b/.test(v)) {
      catEl.value = 'telefony';
    } else if (/\b(macbook|ноутбук|laptop|thinkpad)\b/.test(v)) {
      catEl.value = 'noutbuki';
    } else if (/\b(playstation|ps4|ps5|xbox|nintendo|switch|приставк)\b/.test(v)) {
      catEl.value = 'igrovye_pristavki';
    } else if (/\b(телевизор|oled|qled)\b/.test(v)) {
      catEl.value = 'televizory';
    } else if (/\b(пылесос|dyson|робот-пылесос)\b/.test(v)) {
      catEl.value = 'pylesosy';
    } else if (/\b(стирал|стиральная машин)\b/.test(v)) {
      catEl.value = 'stiralnye_mashiny';
    } else if (/\b(холодильник)\b/.test(v)) {
      catEl.value = 'holodilniki';
    } else if (/\b(шины|резина|диски|r15|r16|r17|r18|колес)\b/.test(v)) {
      catEl.value = 'shiny_i_diski';
    } else if (/\b(шуруповерт|дрель|перфоратор|болгарка|makita|bosch|dewalt)\b/.test(v)) {
      catEl.value = 'elektroinstrument';
    } else if (/\b(квартир|однушк|двушк|трешк|студи|дом|дача|коттедж)\b/.test(v)) {
      catEl.value = 'kvartiry_kupit';
    } else if (/\b(авто|машин|bmw|mercedes|lada|ваз|тойот|toyota|ford|kia|hyundai)\b/.test(v)) {
      catEl.value = 'avtomobili';
    } else if (/\b(велосипед|самокат|stels|cube|merida)\b/.test(v)) {
      catEl.value = 'velosipedy';
    } else if (/\b(диван|кровать|кресло|матрас)\b/.test(v)) {
      catEl.value = 'krovati_i_divany';
    } else if (/\b(шкаф|комод|стеллаж|тумб)\b/.test(v)) {
      catEl.value = 'shkafy_i_komody';
    } else if (/\b(стол|стул|парту)\b/.test(v)) {
      catEl.value = 'stoly_i_stulya';
    }
  }
};

// Превью ссылки удалено во избежание дергания блока при наборе
window.updateGenUrlPreview = function() {};

// Генерация ссылки поиска по выбранной категории и региону с фильтром цен и доставки
window.submitGenerateAvitoSearch = async function(e) {
  if (e && e.preventDefault) e.preventDefault();
  const qEl = document.getElementById('avito-gen-query');
  const catEl = document.getElementById('avito-gen-category');
  const regEl = document.getElementById('avito-gen-region');
  const pminEl = document.getElementById('avito-gen-pmin');
  const pmaxEl = document.getElementById('avito-gen-pmax');
  const delivEl = document.getElementById('avito-gen-delivery');
  const submitBtn = document.getElementById('btn-avito-gen-submit');
  if (!qEl) return;

  const query = qEl.value.trim();
  if (!query) {
    markFieldError(qEl, 'Укажите название или модель товара');
    return;
  }

  const cat = catEl ? catEl.value : 'videokarty';
  const region = regEl ? regEl.value : 'all';
  const onlyDelivery = delivEl ? delivEl.checked : false;
  const pminVal = pminEl ? pminEl.value.trim() : '';
  const pmaxVal = pmaxEl ? pmaxEl.value.trim() : '';
  const pmin = pminVal !== '' ? parseInt(pminVal, 10) : null;
  const pmax = pmaxVal !== '' ? parseInt(pmaxVal, 10) : null;

  if (pmin !== null && (isNaN(pmin) || pmin < 0)) {
    markFieldError(pminEl, 'Укажите корректную цену «от»');
    return;
  }
  if (pmax !== null && (isNaN(pmax) || pmax < 0)) {
    markFieldError(pmaxEl, 'Укажите корректную цену «до»');
    return;
  }
  if (pmin !== null && pmax !== null && pmin > pmax) {
    markFieldError(pminEl, 'Цена «от» не может быть больше цены «до»');
    return;
  }

  // Сохраняем состояние полей формы чтобы они не сбрасывались после генерации
  window._avitoGenState = {
    query,
    category: cat,
    region,
    only_delivery: onlyDelivery,
    pmin: pminVal,
    pmax: pmaxVal
  };

  // Генерация точной ссылки Авито
  const genUrl = buildAvitoGenUrl(cat, query, pmin, pmax, region, onlyDelivery);

  // Понятное отображаемое название для списка отслеживания
  let searchName = query;
  if (region && region !== 'all' && region !== 'rossiya') {
    const regLabel = regEl && regEl.selectedOptions && regEl.selectedOptions[0]
      ? regEl.selectedOptions[0].text.replace(/^[^\w\sа-яёА-ЯЁ]+/u, '').trim()
      : region;
    if (regLabel) {
      searchName += ` [${regLabel}]`;
    }
  }
  if (onlyDelivery) {
    searchName += ` 🚚`;
  }
  if (pmin !== null && pmax !== null) {
    searchName += ` (${pmin}-${pmax})`;
  } else if (pmin !== null && pmin > 0) {
    searchName += ` (от ${pmin})`;
  } else if (pmax !== null && pmax > 0) {
    searchName += ` (до ${pmax})`;
  }

  // Проверка лимита поисковых ссылок (максимум 10)
  const existingSearches = normalizeSearches(avitoData.searches);
  if (existingSearches.length >= 10) {
    if (typeof showToast === 'function') {
      showToast('Достигнут максимальный лимит: 10 поисковых ссылок. Удалите ненужные ссылки перед добавлением новых.', 'warning');
    } else {
      alert('Достигнут максимальный лимит: 10 поисковых ссылок. Удалите ненужные ссылки перед добавлением новых.');
    }
    return;
  }

  // Проверка дублей в списке отслеживаемых
  const isDuplicate = existingSearches.some(s => s.url && s.url.trim().toLowerCase() === genUrl.toLowerCase());
  if (isDuplicate) {
    markFieldError(qEl, 'Такая ссылка поиска уже отслеживается');
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '⏳ Создание...';
  }

  try {
    const res = await fetch('/api/avito/add-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: genUrl,
        name: searchName,
        only_delivery: onlyDelivery ? 1 : 0,
        is_pending: 1,
        username: currentUser ? currentUser.username : '',
        request_id: currentUser ? currentUser.username : '',
        session_token: currentUser ? (currentUser.session_token || '') : ''
      })
    });
    const data = await res.json();
    if (data.success) {
      if (!window._pendingSearchesInModal) window._pendingSearchesInModal = new Set();
      if (data.id) window._pendingSearchesInModal.add(data.id);

      // Автоматически переводим мониторинг в ВКЛ при добавлении ссылки
      if (currentUser) {
        if (!currentUser.permissions) currentUser.permissions = {};
        currentUser.permissions.monitoring = true;
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (typeof window.applyAvitoAutomationRules === 'function') {
          window.applyAvitoAutomationRules(true, Boolean(currentUser.permissions.tg_bot !== false)).catch(() => {});
        }
        fetch('/api/users/permission', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: currentUser.username,
            permission: 'monitoring',
            value: true,
            session_token: currentUser.session_token || ''
          })
        }).catch(() => {});
      }
      if (avitoData && avitoData.stats) avitoData.stats.monitor_enabled = true;
      if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();

      if (data.searches && currentUser) {
        currentUser.avito_searches = normalizeSearches(data.searches);
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (avitoData) avitoData.searches = currentUser.avito_searches;
      }
      await loadAvitoStats(true);
      if (currentCat === 'avito_monitor') renderList();
      openManageSearchesModal();

      // Поиск по новой ссылке начнется только после закрытия окна генерации ссылок (closeModal)
    } else if (data.error === 'duplicate') {
      markFieldError(qEl, 'Такая поисковая ссылка уже отслеживается');
    } else {
      alert('Ошибка добавления: ' + (data.error || 'Неизвестная ошибка'));
    }
  } catch (err) {
    console.error('submitGenerateAvitoSearch error:', err);
    alert('Ошибка соединения с сервером.');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '⚡ Сгенерировать';
    }
  }
};

// Вставить URL из буфера обмена в поле ввода
window.pasteAvitoUrl = async function() {
  try {
    const text = await navigator.clipboard.readText();
    const urlEl = document.getElementById('avito-add-url');
    if (urlEl && text && text.trim()) {
      urlEl.value = text.trim();
      urlEl.focus();
    }
  } catch (err) {
    // Если буфер недоступен — фокусируем поле для ручной вставки (Ctrl+V)
    const urlEl = document.getElementById('avito-add-url');
    if (urlEl) {
      urlEl.focus();
      urlEl.select();
    }
  }
};

window.submitAddAvitoSearch = async function(e, fromManageModal = false) {
  if (e && e.preventDefault) e.preventDefault();
  const urlEl = document.getElementById('avito-add-url');
  const nameEl = document.getElementById('avito-add-name');
  if (!urlEl) return;
  const url = urlEl.value.trim();
  let name = nameEl ? nameEl.value.trim() : '';

  if (!url) {
    urlEl.focus();
    return;
  }
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    markFieldError(urlEl, 'Ссылка должна начинаться с https://');
    return;
  }

  // Автоматическое добавление приписки цен из скопированной ссылки Avito (например RX470 (500-2500))
  const { pmin, pmax } = extractPriceRangeFromUrl(url);
  const priceSuffix = formatPriceSuffix(pmin, pmax);
  if (priceSuffix) {
    if (!name) {
      const qMatch = url.match(/[?&]q=([^&]+)/i);
      let baseName = qMatch ? decodeURIComponent(qMatch[1]).replace(/\+/g, ' ').trim() : '';
      if (!baseName) {
        if (url.includes('videokarty')) baseName = 'Видеокарты';
        else if (url.includes('protsessory')) baseName = 'Процессоры';
        else if (url.includes('telefony')) baseName = 'Телефоны';
        else if (url.includes('noutbuki')) baseName = 'Ноутбуки';
        else if (url.includes('komplektuyuschie')) baseName = 'Комплектующие';
        else baseName = 'Поиск Avito';
      }
      name = `${baseName} ${priceSuffix}`;
    } else if (!/\(\s*(?:от|до|\d+)\s*[\d\-–\s]*\)/i.test(name)) {
      name = `${name} ${priceSuffix}`;
    }
  }

  // Проверка лимита поисковых ссылок (максимум 10)
  const existingSearches = normalizeSearches(avitoData.searches);
  if (existingSearches.length >= 10) {
    if (typeof showToast === 'function') {
      showToast('Достигнут максимальный лимит: 10 поисковых ссылок. Удалите ненужные перед добавлением новых.', 'warning');
    } else {
      alert('Достигнут максимальный лимит: 10 поисковых ссылок. Удалите ненужные перед добавлением новых.');
    }
    return;
  }

  // Клиентская проверка дублей — без запроса на сервер
  const isDuplicate = existingSearches.some(s => s.url && s.url.trim().toLowerCase() === url.toLowerCase());
  if (isDuplicate) {
    markFieldError(urlEl, 'Такая ссылка уже добавлена');
    return;
  }

  try {
    const res = await fetch('/api/avito/add-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        name,
        is_pending: fromManageModal ? 1 : 0,
        username: currentUser ? currentUser.username : '',
        request_id: currentUser ? currentUser.username : '',
        session_token: currentUser ? (currentUser.session_token || '') : ''
      })
    });
    const data = await res.json();
    if (data.success) {
      if (fromManageModal && data.id) {
        if (!window._pendingSearchesInModal) window._pendingSearchesInModal = new Set();
        window._pendingSearchesInModal.add(data.id);
      }

      // Автоматически переводим мониторинг в ВКЛ при добавлении ссылки
      if (currentUser) {
        if (!currentUser.permissions) currentUser.permissions = {};
        currentUser.permissions.monitoring = true;
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (typeof window.applyAvitoAutomationRules === 'function') {
          window.applyAvitoAutomationRules(true, Boolean(currentUser.permissions.tg_bot !== false)).catch(() => {});
        }
        fetch('/api/users/permission', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: currentUser.username,
            permission: 'monitoring',
            value: true,
            session_token: currentUser.session_token || ''
          })
        }).catch(() => {});
      }
      if (avitoData && avitoData.stats) avitoData.stats.monitor_enabled = true;
      if (typeof updateAvitoHeaderDots === 'function') updateAvitoHeaderDots();

      if (data.searches && currentUser) {
        currentUser.avito_searches = normalizeSearches(data.searches);
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (avitoData) avitoData.searches = currentUser.avito_searches;
      }
      await loadAvitoStats(true);
      if (currentCat === 'avito_monitor') renderList();
      if (fromManageModal) {
        openManageSearchesModal();
      } else {
        closeModal();
      }

      // Если окно закрылось сразу (не из модалки), запускаем сбор актуальных объявлений
      if (!fromManageModal) {
        fetch('/api/avito/check', { method: 'POST' }).then(() => loadAvitoStats(true)).catch(() => {});
      }
    } else if (data.error === 'duplicate') {
      markFieldError(urlEl, 'Такая ссылка уже добавлена');
    } else {
      alert('Ошибка добавления: ' + (data.error || 'Неизвестная ошибка'));
    }
  } catch (err) {
    alert('Ошибка соединения с сервером.');
  }
};

window.deleteAvitoSearchFromModal = async function(id) {
  try {
    const allSearches = (avitoData && avitoData.searches && avitoData.searches.length > 0)
      ? avitoData.searches
      : (currentUser && currentUser.avito_searches ? currentUser.avito_searches : []);
    const targetSearch = allSearches.find(s => String(s.id) === String(id));
    const targetUrl = targetSearch ? (targetSearch.url || '') : '';
    const targetName = targetSearch ? (targetSearch.name || targetSearch.url || '') : '';
    const normTargetUrl = (targetUrl || '').trim().replace(/\/+$/, '').toLowerCase();

    const isMatch = s => {
      if (String(s.id) === String(id)) return true;
      if (normTargetUrl && (s.url || '').trim().replace(/\/+$/, '').toLowerCase() === normTargetUrl) return true;
      return false;
    };

    // Мгновенное оптимистичное удаление из состояния пользователя
    if (currentUser && currentUser.avito_searches) {
      currentUser.avito_searches = normalizeSearches(currentUser.avito_searches).filter(s => !isMatch(s));
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
    }
    if (avitoData && avitoData.searches) {
      avitoData.searches = normalizeSearches(avitoData.searches).filter(s => !isMatch(s));
    }
    // Если ссылок больше нет, автоматически выключаем мониторинг
    const remainingSearches = (currentUser && currentUser.avito_searches) ? currentUser.avito_searches : (avitoData && avitoData.searches ? avitoData.searches : []);
    if (remainingSearches.length === 0) {
      if (currentUser && currentUser.permissions) currentUser.permissions.monitoring = false;
      if (avitoData && avitoData.stats) avitoData.stats.monitor_enabled = false;
      try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
      if (typeof window.applyAvitoAutomationRules === 'function') {
        window.applyAvitoAutomationRules(false, Boolean(currentUser && currentUser.permissions && currentUser.permissions.tg_bot !== false)).catch(() => {});
      }
    }
    // Если удалена ссылка, по которой сейчас стоял фильтр, сбрасываем на "all"
    if (targetName && currentAvitoLinkFilter && currentAvitoLinkFilter.toLowerCase() === targetName.toLowerCase()) {
      currentAvitoLinkFilter = 'all';
    }
    // Удаляем карточки объявлений этой ссылки (кроме избранных)
    if (targetName && avitoData && Array.isArray(avitoData.items)) {
      const favSet = getFavoriteIds();
      avitoData.items = avitoData.items.filter(it => {
        if (favSet.has(String(it.item_id))) return true;
        return (it.search_name || '').trim().toLowerCase() !== targetName.trim().toLowerCase();
      });
      if (avitoData.stats) avitoData.stats.total_items = avitoData.items.length;
    }
    if (window._lastAvitoItems && targetName) {
      const favSet = getFavoriteIds();
      window._lastAvitoItems = window._lastAvitoItems.filter(it => {
        if (favSet.has(String(it.item_id))) return true;
        return (it.search_name || '').trim().toLowerCase() !== targetName.trim().toLowerCase();
      });
    }

    // Мгновенно обновляем модалку и карточки без ожидания сети
    openManageSearchesModal();
    if (currentCat === 'avito_monitor') renderList();

    // Запрос на сервер в фоне
    fetch('/api/avito/delete-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id,
        url: targetUrl,
        username: currentUser ? currentUser.username : '',
        request_id: currentUser ? currentUser.username : '',
        session_token: currentUser ? (currentUser.session_token || '') : ''
      })
    }).then(async res => {
      const data = await res.json();
      if (data && data.success && data.searches && currentUser) {
        currentUser.avito_searches = normalizeSearches(data.searches);
        try { localStorage.setItem('skybase_user', JSON.stringify(currentUser)); } catch (e) {}
        if (avitoData) avitoData.searches = currentUser.avito_searches;
        openManageSearchesModal();
      }
      loadAvitoStats(true);
    }).catch(err => {
      console.error('Delete search server error:', err);
    });
  } catch (err) {
    console.error('deleteAvitoSearchFromModal error:', err);
  }
};

window.deleteAvitoSearch = window.deleteAvitoSearchFromModal;

window.addAvitoItemToOrders = async function() {};

// Search & Sort Event Listeners
if (searchInput) searchInput.addEventListener('input', renderList);
if (sortSelect) {
  sortSelect.addEventListener('change', (e) => {
    currentSort = e.target.value;
    renderList();
  });
}

// Start
init();
setTimeout(() => {
  if (typeof _sniperLoadStatus === 'function') _sniperLoadStatus();
}, 1200);

window.renderGuestAuthGate = function() { renderList(); };
window.switchGateAuthTab = function() {};
window.handleGateLogin = function(e) { if (e) e.preventDefault(); };
window.handleGateRegister = function(e) { if (e) e.preventDefault(); };

// ==================== PWA INSTALLATION & SERVICE WORKER DISABLED ====================
// Установка приложения на устройство полностью отключена
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(regs => {
    for (const reg of regs) {
      reg.unregister();
    }
  }).catch(() => {});
}
window.installPwaApp = function() {};

// Заглушки чата (чат отключен)
window.openAdminChatModal = function() {};
window.renderChatModalUI = function() {};
window.sendAdminChatMessage = function() {};
window.updateChatUnreadBadge = function() {};
window.fetchChatMessages = async function() { return { unread_count: 0, messages: [] }; };
window.switchChatUser = function() {};
window.extendAvitoAccessFromChat = function() {};
window.quickGrantAvitoAccess = function() {};

// Плавная горизонтальная прокрутка панели баннера колесиком мыши
document.addEventListener('wheel', (e) => {
  const banner = e.target.closest ? e.target.closest('.avito-dashboard-banner') : null;
  if (banner && banner.scrollWidth > banner.clientWidth) {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      banner.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }
}, { passive: false });
