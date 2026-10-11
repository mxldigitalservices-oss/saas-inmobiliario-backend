/* Sesión compartida (un solo dominio, un solo login).
 *
 * El tipo de sesión se lee del propio JWT (claim "aud"):
 *   "superadmin" -> admin.html      "tenant" -> dashboard.html
 * Así no depende de banderas en localStorage que puedan quedar desfasadas, y no hay
 * bucles de redirección: cada página solo manda al usuario a su página "home" o al login.
 */
(function () {
  function decode(token) {
    try {
      var p = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      while (p.length % 4) p += '=';
      var json = decodeURIComponent(
        atob(p).split('').map(function (c) {
          return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join('')
      );
      return JSON.parse(json);
    } catch (e) { return null; }
  }

  var Session = {
    LOGIN_URL: 'index.html',
    token: function () { return localStorage.getItem('access_token'); },
    claims: function () { var t = this.token(); return t ? decode(t) : null; },
    audience: function () { var c = this.claims(); return c && typeof c.aud === 'string' ? c.aud : null; },
    expired: function () {
      var c = this.claims();
      return !c || !c.exp || c.exp * 1000 <= Date.now() + 5000;
    },
    valid: function () { return !!this.token() && !this.expired(); },
    home: function (aud) { return aud === 'superadmin' ? 'admin.html' : 'dashboard.html'; },
    clear: function () {
      ['access_token', 'refresh_token', 'auth_audience'].forEach(function (k) { localStorage.removeItem(k); });
    },
    logout: function () { this.clear(); window.location.replace(this.LOGIN_URL); },
    /* required: 'tenant' | 'superadmin'. Devuelve true si el usuario puede ver la página. */
    guard: function (required) {
      if (!this.valid()) {
        this.clear();
        window.location.replace(this.LOGIN_URL);
        try { window.stop(); } catch (e) {}
        return false;
      }
      var aud = this.audience();
      if (aud !== required) {
        window.location.replace(this.home(aud));
        try { window.stop(); } catch (e) {}
        return false;
      }
      return true;
    }
  };

  window.Session = Session;

  var me = document.currentScript;
  if (me && me.getAttribute('data-guard')) Session.guard(me.getAttribute('data-guard'));
})();
