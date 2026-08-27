# -*- coding: utf-8 -*-
"""تولید index.html نسخهٔ سرور از روی index.html مشترک ویندوز.

فقط یک بلوک اسکریپت اضافه می‌کند (بدون دست‌زدن به فایل ویندوز):
  - محافظ احراز هویت (بازگشت به /login در صورت نبود نشست یا اجبار تغییر رمز)
  - دکمهٔ «خروج» → خروج از حساب (نه خاموش‌کردن سرویس)
  - کارت «پروفایل‌های ریموت»: باز/بستن نشست noVNC + «کپچا حل شد»

اجرا:  python3 server/scripts/build_static.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "marketing_divar" / "web" / "static" / "index.html"
DST = ROOT / "server" / "divar_server" / "static" / "index.html"

INJECT = r"""
<!-- ══════════ تزریق نسخهٔ سرور (خودکار توسط build_static.py) ══════════ -->
<script>
(function(){
  /* محافظ احراز هویت */
  fetch('/api/auth/status').then(function(r){return r.json();}).then(function(s){
    if(!s.authenticated || s.must_change_password){ location.href='/login'; }
  }).catch(function(){});

  /* خروج از حساب به‌جای خاموش‌کردن سرویس */
  window.quitApp = function(){
    if(!confirm('از حساب خارج شوید؟')) return;
    fetch('/api/auth/logout',{method:'POST'}).finally(function(){ location.href='/login'; });
  };

  /* کارت پروفایل‌های ریموت */
  function remoteCard(){
    var list = document.getElementById('accounts-list');
    if(!list || document.getElementById('remote-card')) return;
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 'remote-card';
    card.style.marginTop = '14px';
    card.innerHTML =
      '<h3>🖥️ پروفایل‌های ریموت (سرور) ' +
        '<span class="q">؟<span class="qtip">برای هر اکانت یک مرورگر Chromium واقعی روی سرور (Xvfb) باز می‌شود و تصویر آن از طریق noVNC داخل مرورگر شما می‌آید. برای لاگین اولیه یا حل دستی کپچا استفاده کنید؛ بعد از اتمام «بستن» را بزنید. هیچ حل خودکار کپچایی وجود ندارد.</span></span>' +
      '</h3><div id="remote-list"><div class="empty">در حال بارگذاری…</div></div>';
    list.closest('.card').insertAdjacentElement('beforebegin', card);
  }

  window.remoteRefresh = function(){
    remoteCard();
    var box = document.getElementById('remote-list');
    if(!box) return;
    Promise.all([
      fetch('/api/accounts').then(function(r){return r.json();}),
      fetch('/api/remote/sessions').then(function(r){return r.json();})
    ]).then(function(res){
      var accs = (res[0].accounts||[]).map(function(a){return a.name;});
      var sess = res[1].sessions || {};
      if(!accs.length){
        box.innerHTML = '<div class="empty">اکانتی ثبت نشده — اول در تب اکانت‌ها پروفایل بسازید</div>';
        return;
      }
      box.innerHTML = accs.map(function(n){
        var open = !!sess[n];
        var st = open ? (sess[n].idle_sec || 0) : 0;
        var view = open ? ('<a class="btn sm ok" href="/novnc/vnc.html?path=/api/remote/' +
            encodeURIComponent(n) + '/ws&autoconnect=1" target="_blank">👁️ مشاهده</a>') : '';
        var btn = open
          ? '<button class="btn sm err" onclick="remoteClose(\'' + n.replace(/'/g,"") + '\')">بستن نشست</button>'
          : '<button class="btn sm" onclick="remoteOpen(\'' + n.replace(/'/g,"") + '\')">باز کردن پروفایل</button>';
        return '<div class="acc"><div class="row"><b>' + n + '</b>' +
          (open ? '<span class="tag ok">باز' + (st ? ' · ' + Math.round(st) + 's بی‌کار' : '') + '</span>'
                : '<span class="tag gray">بسته</span>') +
          '</div><div class="row">' + btn + view +
          '<button class="btn sm gray" onclick="remoteVerify(\'' + n.replace(/'/g,"") + '\')">کپچا حل شد / ادامه</button>' +
          '</div></div>';
      }).join('');
    }).catch(function(){});
  };

  window.remoteOpen = function(name){
    fetch('/api/remote/' + encodeURIComponent(name) + '/open', {method:'POST'})
      .then(function(r){return r.json().then(function(d){return {s:r.status,d:d};});})
      .then(function(x){
        if(x.s===200 && x.d.ok){
          toast('نشست باز شد — لینک مشاهده در حال باز شدن…');
          window.open('/novnc/vnc.html?path=/api/remote/' + encodeURIComponent(name) + '/ws&autoconnect=1','_blank');
          remoteRefresh();
        } else { toast('❌ ' + (x.d.message || 'خطا'), false); }
      }).catch(function(e){ toast('❌ ' + e.message, false); });
  };

  window.remoteClose = function(name){
    fetch('/api/remote/' + encodeURIComponent(name) + '/close', {method:'POST'})
      .then(function(r){return r.json();})
      .then(function(d){ toast(d.message || 'بسته شد', d.ok!==false); remoteRefresh(); })
      .catch(function(e){ toast('❌ ' + e.message, false); });
  };

  window.remoteVerify = function(name){
    fetch('/api/accounts/captcha-cleared', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({name:name})})
      .then(function(r){return r.json();})
      .then(function(d){ toast(d.message || 'انجام شد', d.cleared!==false); remoteRefresh(); accRefresh(); refreshStatus(); })
      .catch(function(e){ toast('❌ ' + e.message, false); });
  };

  remoteRefresh();
  setInterval(remoteRefresh, 8000);
})();
</script>
<!-- ══════════ پایان تزریق نسخهٔ سرور ══════════ -->
"""


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    if "تزریق نسخهٔ سرور" in src:
        raise SystemExit("منبع از قبل تزریق شده — متوقف")
    dst = src.replace("</body>", INJECT + "\n</body>")
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(dst, encoding="utf-8")
    print(f"نوشته شد: {DST}")


if __name__ == "__main__":
    main()
