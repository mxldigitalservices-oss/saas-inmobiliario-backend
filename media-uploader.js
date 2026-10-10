/* Módulo de multimedia (fotos y videos) para propiedades y unidades.
 *
 * Uso:
 *   MediaUploader.open({ ownerType: 'property' | 'unit', ownerId: '<id>', title: '...', onChange: fn });
 *
 * - Móvil / tablet: toca la zona de carga para elegir de la galería (selección múltiple)
 *   o usa "Tomar foto o video" para abrir la cámara.
 * - Escritorio: arrastra y suelta archivos o haz clic para seleccionar varios a la vez.
 *
 * Endpoints:
 *   GET/POST /api/v1/properties/{id}/media      POST /api/v1/properties/{id}/media/{mediaId}/cover
 *   GET/POST /api/v1/units/{id}/media           DELETE /api/v1/media/{mediaId}
 */
(function () {
  'use strict';

  var API = '/api/v1';
  var MAX_IMAGE_MB = 15;
  var MAX_VIDEO_MB = 60;
  var MAX_VIDEO_SECONDS = 15;
  var CONCURRENCY = 2;
  var IMAGE_EXT = /\.(jpe?g|png|webp|gif)$/i;
  var VIDEO_EXT = /\.(mp4|webm|mov)$/i;

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function token() { return localStorage.getItem('access_token'); }
  function fmtSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
    return Math.max(1, Math.round(bytes / 1024)) + ' KB';
  }
  function errorMessage(data, fallback) {
    if (!data) return fallback;
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail) && data.detail[0] && data.detail[0].msg) return data.detail[0].msg;
    if (data.detail && data.detail.message) return data.detail.message;
    return fallback;
  }
  function unauthorized() {
    if (window.Session) window.Session.logout();
    else { localStorage.removeItem('access_token'); window.location.replace('index.html'); }
  }

  function kindOf(file) {
    var t = (file.type || '').toLowerCase();
    if (t.indexOf('image/') === 0) return 'image';
    if (t.indexOf('video/') === 0) return 'video';
    if (IMAGE_EXT.test(file.name)) return 'image';
    if (VIDEO_EXT.test(file.name)) return 'video';
    return null;
  }

  /* Duración del video leída en el navegador. Resuelve null si no se puede leer. */
  function videoDuration(file) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(file);
      var v = document.createElement('video');
      var done = false;
      function finish(value) {
        if (done) return;
        done = true;
        URL.revokeObjectURL(url);
        resolve(value);
      }
      v.preload = 'metadata';
      v.muted = true;
      v.onloadedmetadata = function () { finish(isFinite(v.duration) ? v.duration : null); };
      v.onerror = function () { finish(null); };
      setTimeout(function () { finish(null); }, 6000);
      v.src = url;
    });
  }

  function validate(file) {
    var kind = kindOf(file);
    if (!kind) return Promise.resolve('Formato no admitido (usa JPG, PNG, WebP, MP4, WebM o MOV)');
    var limit = (kind === 'image' ? MAX_IMAGE_MB : MAX_VIDEO_MB) * 1048576;
    if (file.size > limit) {
      return Promise.resolve('Pesa ' + fmtSize(file.size) + '; el máximo es ' + (kind === 'image' ? MAX_IMAGE_MB : MAX_VIDEO_MB) + ' MB');
    }
    if (kind === 'video') {
      return videoDuration(file).then(function (d) {
        if (d != null && d > MAX_VIDEO_SECONDS + 0.5) {
          return 'Dura ' + Math.round(d) + ' s; el máximo es ' + MAX_VIDEO_SECONDS + ' s';
        }
        return null;
      });
    }
    return Promise.resolve(null);
  }

  function open(opts) {
    opts = opts || {};
    var ownerType = opts.ownerType === 'unit' ? 'unit' : 'property';
    var ownerId = String(opts.ownerId || '');
    if (!ownerId) return;
    var base = API + (ownerType === 'unit' ? '/units/' : '/properties/') + encodeURIComponent(ownerId) + '/media';

    var state = { media: [], coverId: null, queue: [], changed: false, nextId: 1 };
    var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

    // ---------- DOM ----------
    var root = document.createElement('div');
    root.className = 'fixed inset-0 z-[70] flex items-end justify-center bg-slate-900/50 backdrop-blur-sm sm:items-center sm:p-4';
    root.innerHTML =
      '<div class="flex max-h-[94vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-xl sm:max-h-[90vh] sm:rounded-2xl" role="dialog" aria-modal="true">' +
        '<div class="flex items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 sm:px-6">' +
          '<div class="min-w-0">' +
            '<h2 class="truncate text-lg font-bold text-slate-900">' + esc(opts.title || 'Fotos y videos') + '</h2>' +
            '<p class="mt-0.5 text-xs text-slate-500">Imágenes hasta ' + MAX_IMAGE_MB + ' MB · Videos MP4/WebM/MOV de máx. ' + MAX_VIDEO_SECONDS + ' s y ' + MAX_VIDEO_MB + ' MB</p>' +
          '</div>' +
          '<button type="button" data-mu="close" aria-label="Cerrar" class="flex-none rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600">' +
            '<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>' +
          '</button>' +
        '</div>' +
        '<div class="flex-1 overflow-y-auto px-4 py-5 sm:px-6">' +
          '<label data-mu="drop" class="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40">' +
            '<svg class="h-10 w-10 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A1.5 1.5 0 0021.75 19.5v-15A1.5 1.5 0 0020.25 3H3.75A1.5 1.5 0 002.25 4.5v15A1.5 1.5 0 003.75 21zM15.75 8.25h.008v.008h-.008V8.25z"/></svg>' +
            '<p class="mt-3 text-sm font-semibold text-slate-800">' + (touch ? 'Toca para elegir de tu galería' : 'Arrastra y suelta aquí, o haz clic para elegir') + '</p>' +
            '<p class="mt-1 text-xs text-slate-500">Puedes seleccionar varios archivos a la vez</p>' +
            '<input data-mu="input" type="file" multiple accept="image/*,video/*" class="hidden">' +
          '</label>' +
          (touch
            ? '<label class="mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700">' +
                '<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"/><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z"/></svg>' +
                'Tomar foto o video' +
                '<input data-mu="camera" type="file" accept="image/*,video/*" capture="environment" class="hidden">' +
              '</label>'
            : '') +
          '<ul data-mu="queue" class="mt-4 space-y-2"></ul>' +
          '<div class="mt-6 flex items-center justify-between">' +
            '<h3 class="text-sm font-semibold text-slate-700">Archivos subidos <span data-mu="count" class="font-normal text-slate-400"></span></h3>' +
          '</div>' +
          '<p data-mu="gallery-msg" class="mt-3 text-sm text-slate-400">Cargando…</p>' +
          '<div data-mu="gallery" class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4"></div>' +
        '</div>' +
        '<div class="flex justify-end border-t border-slate-100 px-4 py-3 sm:px-6">' +
          '<button type="button" data-mu="close" class="rounded-xl bg-slate-50 px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100">Listo</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(root);
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function q(name) { return root.querySelector('[data-mu="' + name + '"]'); }
    var elQueue = q('queue');
    var elGallery = q('gallery');
    var elMsg = q('gallery-msg');
    var elCount = q('count');
    var elDrop = q('drop');

    function close() {
      document.removeEventListener('keydown', onKey);
      state.queue.forEach(function (it) { if (it.xhr && it.status === 'uploading') it.xhr.abort(); });
      state.queue.forEach(function (it) { if (it.preview) URL.revokeObjectURL(it.preview); });
      document.body.style.overflow = prevOverflow;
      root.remove();
      if (state.changed && typeof opts.onChange === 'function') opts.onChange();
    }
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);
    root.addEventListener('click', function (e) {
      if (e.target === root || e.target.closest('[data-mu="close"]')) close();
    });

    // ---------- API ----------
    function request(method, url) {
      return fetch(url, { method: method, headers: { 'Authorization': 'Bearer ' + token(), 'Accept': 'application/json' } })
        .then(function (res) {
          if (res.status === 401) { unauthorized(); throw new Error('Sesión expirada'); }
          if (res.status === 204) return null;
          return res.json().catch(function () { return null; }).then(function (data) {
            if (!res.ok) throw new Error(errorMessage(data, 'Error ' + res.status));
            return data;
          });
        });
    }

    function loadGallery() {
      var jobs = [request('GET', base)];
      if (ownerType === 'property') {
        jobs.push(request('GET', API + '/properties/' + encodeURIComponent(ownerId)).catch(function () { return null; }));
      }
      return Promise.all(jobs).then(function (res) {
        state.media = Array.isArray(res[0]) ? res[0] : [];
        state.coverId = res[1] && res[1].cover_media_id ? String(res[1].cover_media_id) : null;
        renderGallery();
      }).catch(function (err) {
        elMsg.textContent = err.message || 'No se pudo cargar la galería';
        elMsg.className = 'mt-3 text-sm text-rose-600';
      });
    }

    function renderGallery() {
      elCount.textContent = state.media.length ? '(' + state.media.length + ')' : '';
      if (!state.media.length) {
        elMsg.textContent = 'Todavía no hay fotos ni videos.';
        elMsg.className = 'mt-3 text-sm text-slate-400';
        elGallery.innerHTML = '';
        return;
      }
      elMsg.className = 'hidden';
      elGallery.innerHTML = state.media.map(function (m) {
        var id = String(m.id || m._id);
        var st = m.storage || {};
        var isCover = state.coverId === id;
        var visual = m.kind === 'video'
          ? '<video src="' + esc(st.url) + '#t=0.1" preload="metadata" controls playsinline class="h-full w-full object-cover"></video>'
          : '<img src="' + esc(st.thumb_url || st.url) + '" alt="" loading="lazy" class="h-full w-full object-cover">';
        var coverBtn = (ownerType === 'property' && m.kind === 'image')
          ? (isCover
              ? '<span class="absolute bottom-2 left-2 rounded-full bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow">★ Portada</span>'
              : '<button type="button" data-mu-cover="' + esc(id) + '" class="absolute bottom-2 left-2 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-slate-700 shadow transition hover:bg-white">☆ Portada</button>')
          : '';
        var tag = m.kind === 'video'
          ? '<span class="absolute left-2 top-2 rounded-full bg-slate-900/70 px-2 py-0.5 text-[11px] font-medium text-white">Video</span>'
          : '';
        return '<div class="relative aspect-square overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200">' +
          visual + tag + coverBtn +
          '<button type="button" data-mu-del="' + esc(id) + '" aria-label="Eliminar" class="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-rose-600 shadow transition hover:bg-rose-50">' +
            '<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>' +
          '</button>' +
        '</div>';
      }).join('');
    }

    elGallery.addEventListener('click', function (e) {
      var del = e.target.closest('[data-mu-del]');
      var cov = e.target.closest('[data-mu-cover]');
      if (del) {
        if (!window.confirm('¿Eliminar este archivo? Esta acción no se puede deshacer.')) return;
        del.disabled = true;
        request('DELETE', API + '/media/' + encodeURIComponent(del.getAttribute('data-mu-del')))
          .then(function () { state.changed = true; return loadGallery(); })
          .catch(function (err) { del.disabled = false; window.alert(err.message); });
      } else if (cov) {
        cov.disabled = true;
        request('POST', base + '/' + encodeURIComponent(cov.getAttribute('data-mu-cover')) + '/cover')
          .then(function () { state.changed = true; state.coverId = cov.getAttribute('data-mu-cover'); renderGallery(); })
          .catch(function (err) { cov.disabled = false; window.alert(err.message); });
      }
    });

    // ---------- Cola de subida ----------
    function renderQueue() {
      elQueue.innerHTML = state.queue.map(function (it) {
        var thumb = it.kind === 'video'
          ? '<div class="flex h-12 w-12 flex-none items-center justify-center rounded-lg bg-slate-800 text-white"><svg class="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>'
          : '<img src="' + esc(it.preview) + '" alt="" class="h-12 w-12 flex-none rounded-lg object-cover">';
        var right;
        if (it.status === 'error') {
          right = '<p class="mt-0.5 text-xs text-rose-600">' + esc(it.error) + '</p>';
        } else if (it.status === 'done') {
          right = '<p class="mt-0.5 text-xs text-emerald-600">Subido ✓</p>';
        } else {
          var label = it.status === 'validating' ? 'Revisando…' : it.status === 'queued' ? 'En espera' : (it.progress >= 100 ? 'Procesando…' : it.progress + '%');
          right = '<div class="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-indigo-500 transition-all" style="width:' + (it.status === 'uploading' ? it.progress : 0) + '%"></div></div>' +
                  '<p class="mt-1 text-xs text-slate-500">' + label + '</p>';
        }
        var dismiss = (it.status === 'error' || it.status === 'done')
          ? '<button type="button" data-mu-dismiss="' + it.id + '" aria-label="Quitar de la lista" class="flex-none rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600">✕</button>'
          : '';
        return '<li class="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-2.5">' + thumb +
          '<div class="min-w-0 flex-1"><p class="truncate text-sm font-medium text-slate-800">' + esc(it.file.name) + ' <span class="font-normal text-slate-400">· ' + fmtSize(it.file.size) + '</span></p>' + right + '</div>' + dismiss + '</li>';
      }).join('');
    }
    elQueue.addEventListener('click', function (e) {
      var b = e.target.closest('[data-mu-dismiss]');
      if (!b) return;
      var id = Number(b.getAttribute('data-mu-dismiss'));
      state.queue = state.queue.filter(function (it) {
        if (it.id === id && it.preview) URL.revokeObjectURL(it.preview);
        return it.id !== id;
      });
      renderQueue();
    });

    function uploadItem(it) {
      return new Promise(function (resolve) {
        var xhr = new XMLHttpRequest();
        it.xhr = xhr;
        it.status = 'uploading';
        it.progress = 0;
        renderQueue();
        xhr.open('POST', base);
        xhr.setRequestHeader('Authorization', 'Bearer ' + token());
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.upload.onprogress = function (ev) {
          if (ev.lengthComputable) {
            it.progress = Math.min(100, Math.round((ev.loaded / ev.total) * 100));
            renderQueue();
          }
        };
        xhr.onload = function () {
          var data = null;
          try { data = JSON.parse(xhr.responseText); } catch (e) { /* sin JSON */ }
          if (xhr.status === 401) { unauthorized(); return resolve(); }
          if (xhr.status >= 200 && xhr.status < 300) {
            it.status = 'done';
            state.changed = true;
          } else {
            it.status = 'error';
            it.error = errorMessage(data, 'No se pudo subir (error ' + xhr.status + ')');
          }
          renderQueue();
          resolve();
        };
        xhr.onerror = function () { it.status = 'error'; it.error = 'Error de conexión'; renderQueue(); resolve(); };
        xhr.onabort = function () { resolve(); };
        var fd = new FormData();
        fd.append('file', it.file, it.file.name);
        xhr.send(fd);
      });
    }

    var running = 0;
    function pump() {
      while (running < CONCURRENCY) {
        var next = state.queue.find(function (it) { return it.status === 'queued'; });
        if (!next) break;
        running++;
        uploadItem(next).then(function () {
          running--;
          pump();
          if (!state.queue.some(function (it) { return it.status === 'queued' || it.status === 'uploading'; })) {
            loadGallery();
          }
        });
      }
    }

    function addFiles(fileList) {
      Array.prototype.slice.call(fileList || []).forEach(function (file) {
        var kind = kindOf(file);
        var it = {
          id: state.nextId++, file: file, kind: kind || 'image', status: 'validating',
          progress: 0, error: '', preview: kind === 'image' ? URL.createObjectURL(file) : null
        };
        state.queue.push(it);
        renderQueue();
        validate(file).then(function (problem) {
          if (problem) { it.status = 'error'; it.error = problem; renderQueue(); return; }
          it.status = 'queued';
          renderQueue();
          pump();
        });
      });
    }

    // ---------- Selección / arrastrar y soltar ----------
    ['input', 'camera'].forEach(function (name) {
      var input = q(name);
      if (!input) return;
      input.addEventListener('change', function () { addFiles(input.files); input.value = ''; });
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
      elDrop.addEventListener(ev, function (e) {
        e.preventDefault();
        elDrop.classList.add('border-indigo-500', 'bg-indigo-50');
      });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      elDrop.addEventListener(ev, function (e) {
        e.preventDefault();
        elDrop.classList.remove('border-indigo-500', 'bg-indigo-50');
      });
    });
    elDrop.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
    });
    // Evita que soltar un archivo fuera de la zona abra el archivo en el navegador
    root.addEventListener('dragover', function (e) { e.preventDefault(); });
    root.addEventListener('drop', function (e) { e.preventDefault(); });

    loadGallery();
  }

  window.MediaUploader = { open: open };
})();
