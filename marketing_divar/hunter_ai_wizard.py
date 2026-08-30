# -*- coding: utf-8 -*-
"""تنظیمات شکارچی با کمک AI — چت خودمونی پرانرژی."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .matching import normalize

IPHONE_PATTERN = re.compile(r"(?:iphone|آیفون)\s*([0-9]{1,2})\s*(?:pro\s*max|pro|plus|mini|promax)?", re.I)
IPHONE_FA_PATTERN = re.compile(r"آیفون\s*([0-9]{1,2})", re.I)

BRAND_MODELS = {
    "iphone": ["آیفون", "iphone"],
    "samsung": ["سامسونگ", "samsung", "گلکسی", "galaxy"],
    "xiaomi": ["شیائومی", "xiaomi", "redmi", "poco"],
    "laptop": ["لپ تاپ", "لپ‌تاپ", "لپتاپ", "نوت بوک", "macbook", "مک بوک"],
    "pride": ["پراید", "111", "131", "132"],
}


def _parse_price_to_toman(text: str) -> Optional[int]:
    if not text:
        return None
    t = text.replace("،", ",").strip()
    m = re.search(r"(\d+[\d,\.]*)\s*(میلیون|تومن|تومان|هزار|m|k)?", t, re.I)
    if not m:
        return None
    num_s = m.group(1).replace(",", "").replace(".", "")
    try:
        num = float(num_s)
    except:
        return None
    unit = (m.group(2) or "").lower()
    if "میلیون" in unit or unit == "m":
        return int(num * 1_000_000)
    if "هزار" in unit or unit == "k":
        return int(num * 1000)
    if num < 1000:
        return int(num * 1_000_000)
    return int(num)


def extract_products_from_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    n = normalize(text)
    products: List[Dict[str, Any]] = []
    seen_models = set()
    iphone_strong = re.compile(r"(?:iphone|آیفون)\s*(X[SR]?|XS\s*Max|1[0-5]|1[0-2])\s*(Pro\s*Max|Pro|Plus|Mini|promax)?", re.I)
    for m in iphone_strong.finditer(text):
        ver = (m.group(1) or "").strip()
        extra = (m.group(2) or "").strip()
        ver_clean = ver.replace(" ", "").upper() if ver.upper().startswith("X") else ver
        if ver_clean.lower().startswith("xs"):
            ver_clean = "XS"
        full = f"آیفون {ver_clean}"
        if extra:
            ex_low = extra.lower().replace(" ", "")
            if "promax" in ex_low or "pro max" in extra.lower():
                full = f"آیفون {ver_clean} Pro Max"
            elif "pro" in ex_low:
                full = f"آیفون {ver_clean} Pro"
            elif "plus" in ex_low:
                full = f"آیفون {ver_clean} Plus"
            elif "mini" in ex_low:
                full = f"آیفون {ver_clean} Mini"
        if full not in seen_models:
            seen_models.add(full)
            products.append({"model": full, "brand": "apple", "family": "phone", "keyword": full, "category": "mobile-phones"})
    for m in IPHONE_PATTERN.finditer(text):
        ver = m.group(1)
        full = f"آیفون {ver}"
        extra = m.group(0).lower()
        if "pro max" in extra or "promax" in extra:
            full = f"آیفون {ver} Pro Max"
        elif "pro" in extra:
            full = f"آیفون {ver} Pro"
        elif "plus" in extra:
            full = f"آیفون {ver} Plus"
        elif "mini" in extra:
            full = f"آیفون {ver} Mini"
        if full not in seen_models:
            seen_models.add(full)
            products.append({"model": full, "brand": "apple", "family": "phone", "keyword": full, "category": "mobile-phones"})
    if products or "آیفون" in text or "iphone" in text.lower():
        nums = re.findall(r"(?<!\w)(X[SR]?|1[0-5]|1[0-2])(?!\w)", text, re.I)
        for num in nums:
            num_clean = num.strip().upper() if num.upper().startswith("X") else num.strip()
            full = f"آیفون {num_clean}"
            if full not in seen_models:
                seen_models.add(full)
                products.append({"model": full, "brand": "apple", "family": "phone", "keyword": full, "category": "mobile-phones"})
    if not products:
        kw = text.strip()[:80]
        if len(kw) >= 2:
            fam = "generic"
            cat = ""
            if any(normalize(w) in n for w in BRAND_MODELS["iphone"]):
                fam = "phone"
                cat = "mobile-phones"
            elif any(normalize(w) in n for w in BRAND_MODELS["samsung"]):
                fam = "phone"
                cat = "samsung"
            elif any(normalize(w) in n for w in BRAND_MODELS["laptop"]):
                fam = "laptop"
                cat = "laptops"
            elif any(normalize(w) in n for w in BRAND_MODELS["pride"]):
                fam = "vehicle"
                cat = "light"
            products.append({"model": kw, "brand": "", "family": fam, "keyword": kw, "category": cat})
    return products


def extract_numbers(text: str) -> List[int]:
    out = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(میلیون|تومان|هزار|درصد|%|m)?", text):
        val = _parse_price_to_toman(m.group(0))
        if val:
            out.append(val)
    return out


def extract_quantity(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d+)\s*(?:تا|عدد|دونه)", text)
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 1000:
                return v
        except:
            pass
    m = re.search(r"هر\s*مدل\s*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    m = re.search(r"تعداد[:\s]*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    if any(w in text for w in ["تا میخوام", "تا بخریم", "تعداد", "هر مدل"]):
        nums = re.findall(r"\b(\d{1,3})\b", text)
        for ns in nums:
            try:
                v = int(ns)
                if 1 <= v <= 100:
                    return v
            except:
                pass
    return None


def extract_conditions(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"[،,]\s*", text)
    conds = []
    keywords = ["تمیز", "بدون تعمیر", "بدون خط", "سالم", "باتری", "کارکرده", "نو", "بدون خش", "پلمپ", "رجیستر", "بدون رجیستر", "اصل", "فابریک", "بدون تعویض"]
    for p in parts:
        pp = p.strip()
        if not pp:
            continue
        if any(k in pp for k in keywords) or len(pp) <= 30:
            if "میلیون" in pp or "سود" in pp or "قیمت" in pp:
                continue
            if pp not in conds and len(pp) >= 2:
                conds.append(pp)
    for k in keywords:
        if k in text and k not in conds and len(k) > 2:
            if not any(k in c for c in conds):
                conds.append(k)
    return conds[:8]


GREETINGS = [
    "سلام رفیق 😍 حالت چطوره؟ چه خبر؟ امروز قراره با هم یه شکار خفن بزنیم!",
    "درود بزرگوار 🌹 خیلی خوش اومدی! آماده‌ای بترکونیم بازار رو؟",
    "سلام سلام! 👋 انرژی‌ات عالیه، بگو ببینم امروز دنبال چی هستیم؟",
    "ای جان! 😎 اومدی که یه سود حسابی ببریم؟ بگو چی تو ذهنته؟",
]

ASK_PRODUCTS = [
    "خب بگو ببینم، دقیقا دنبال چه دستگاهایی هستی؟ مثلا آیفون 12، 13، 14، 15؟ یا چیز دیگه؟ هرچی تو ذهنته همینجوری خودمونی بگو 👇",
    "عالیه! حالا بهم بگو چه مدلایی مد نظرته؟ آیفون؟ سامسونگ؟ لپ تاپ؟ ماشین؟ هرچی هست راحت بگو، من می‌فهمم 😉",
]

ASK_SELL_PRICE = [
    "دمت گرم! {model} رو به شرط سالم بودن حدودا چقدر می‌تونی بفروشی؟ مثلا 40 میلیون؟ یه عدد بده که بدونم سقف بازار چقدره 💰",
    "ایول، {model} انتخاب خفنیه! 🔥 به نظرت همین الان تو بازار، سالم و تمیز، چقدر میره؟ قیمت فروش خودت چقدره؟",
]

ASK_PROFIT = [
    "خب حالا رو {model} چقدر می‌خوای سود کنی؟ مثلا 3 میلیون؟ یا 5 میلیون؟ بهم بگو تا تنظیم کنم سودت چقدر باشه 🎯",
    "سوال مهم! 💡 رو {model} چقدر سود برات خوبه؟ مثلا میگی 10% یا مثلا 4 میلیون؟ بگو تا شکارچی رو دقیق تنظیم کنم",
    "باشه، حالا بگو رو {model} چند تا چند سود می‌خوای؟ مثلا بگو 2 تا 5 میلیون خوبه، یا حداقل 10 درصد؟",
]

ASK_QUANTITY = [
    "چند تا از {model} می‌خوای بخری؟ مثلا 2 تا؟ یا هرچی پیدا شد؟",
    "تعدادش چطور؟ می‌خوای هرچی قیمت خوب بود بگیرم یا مثلا ماهی 5 تا؟",
    "هر مدل چند تا می‌خوای؟ مثلا بگو هر کدوم 5 تا، یا کلا 10 تا؟ 🔢",
]

ASK_CONDITIONS = [
    "شرایط دستگاه چطور باشه؟ مثلا میگی فقط تمیز و بدون تعمیر؟ یا باتری بالای 85؟ هر شرطی داری بگو تا فیلتر کنم 🧹",
    "چه شرایطی برات مهمه؟ مثلا بدون تعمیر، بدون خط و خش، باتری بالا؟ بگو تا شکارچی فقط همونارو بیاره ✨",
]

FINAL_OK = [
    "اوکی رفیق! تنظیماتت آماده‌ست 🚀 الان می‌تونی دکمه «ست کردن تنظیمات» رو بزنی تا خودکار همه چی ست بشه. دیگه شکارچی با همین سود و قیمت برات می‌گرده!",
    "حله! همه چی رو گرفتم ✅ تنظیمات حرفه‌ای‌ت آماده‌ست. فقط دکمه پایین رو بزن تا ست بشه. نکته‌ای هم هست بگو!",
]


def _pick(arr: List[str]) -> str:
    import random
    return random.choice(arr)


def _is_model_ready() -> bool:
    try:
        from .nlu_model import is_ready, backend_name
        if not is_ready():
            return False
        bn = backend_name()
        if bn == "none":
            return False
        if "fallback" in bn:
            return False
        return True
    except Exception:
        return False


def _llm_chat(prompt: str) -> str:
    try:
        from .nlu_model import gguf_path, llama_exe, _has_llama_cpp_python
        import subprocess, sys
        full_prompt = (
            "تو یک دستیار خرید و فروش حرفه‌ای، صمیمی، پرانرژی، تهرانی هستی.\n"
            "کاربر می‌خواد دستگاه دست دوم بخره و بفروشه سود کنه.\n"
            "خیلی خودمونی، با ایموجی، با انرژی صحبت کن. مثل رفیق.\n"
            "سوال رو کوتاه بپرس، نه طولانی.\n"
            f"متن کاربر: {prompt}\n"
            "پاسخ تو (فارسی، خودمونی، کوتاه):"
        )
        if _has_llama_cpp_python():
            try:
                from llama_cpp import Llama
                g = gguf_path()
                model = Llama(model_path=str(g), n_ctx=1024, n_threads=4, verbose=False)
                out = model.create_completion(prompt=full_prompt, max_tokens=180, temperature=0.8, stop=["\n\n"])
                txt = (out.get("choices") or [{}])[0].get("text") or ""
                txt = txt.strip()
                if txt:
                    return txt[:400]
            except Exception:
                pass
        exe = llama_exe()
        g = gguf_path()
        if exe and g.exists():
            cmd = [str(exe), "-m", str(g), "-n", "180", "-c", "1024", "--temp", "0.8", "-p", full_prompt, "-no-cnv"]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=20,
                                   creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0)
                out = (r.stdout or b"").decode("utf-8", errors="replace")
                if full_prompt in out:
                    out = out.split(full_prompt)[-1]
                out = out.strip().split("\n")[0].strip()
                if out:
                    return out[:400]
            except Exception:
                pass
    except Exception:
        pass
    return ""


def generate_ai_message(step: str, context: Dict[str, Any]) -> str:
    if _is_model_ready():
        try:
            prompt_map = {
                "greeting": "کاربر تازه اومده، سلام پرانرژی خودمونی بگو و بپرس دنبال چی هستی برای خرید و فروش",
                "ask_products": f"کاربر گفت: {context.get('last_user','')}. بپرس دقیقا چه مدلایی مد نظرشه",
                "ask_sell_price": f"مدل {context.get('model','')} انتخاب شده. بپرس به شرط سالم چقدر می‌تونه بفروشه",
                "ask_profit": f"مدل {context.get('model','')} قیمت فروش {context.get('sell_price','')}. بپرس چقدر سود می‌خواد",
                "ask_quantity": f"مدل {context.get('model','')} سود {context.get('profit','')}. بپرس چند تا می‌خواد",
                "ask_conditions": "بپرس شرایط دستگاه چطور باشه",
                "confirm": "جمع‌بندی کن چی فهمیدی و بپرس اوکیه",
                "done": "بگو تنظیمات آماده‌ست و دکمه ست کردن رو بزنه",
            }
            llm_out = _llm_chat(prompt_map.get(step, "سلام خودمونی بگو"))
            if llm_out and len(llm_out) > 10:
                return llm_out
        except Exception:
            pass

    if step == "greeting":
        return _pick(GREETINGS) + "\n\n" + _pick(ASK_PRODUCTS)
    if step == "ask_products":
        return _pick(ASK_PRODUCTS)
    if step == "ask_sell_price":
        model = context.get("model", "این دستگاه")
        return _pick(ASK_SELL_PRICE).format(model=model)
    if step == "ask_profit":
        model = context.get("model", "این دستگاه")
        return _pick(ASK_PROFIT).format(model=model)
    if step == "ask_quantity":
        model = context.get("model", "این دستگاه")
        try:
            return _pick(ASK_QUANTITY).format(model=model)
        except:
            return _pick(ASK_QUANTITY)
    if step == "ask_conditions":
        return _pick(ASK_CONDITIONS)
    if step == "confirm":
        prods = context.get("products", [])
        lines = ["خب بذار ببینم درست فهمیدم 👇\n"]
        for p in prods:
            sp = p.get("sell_price", 0)
            pr = p.get("profit", 0)
            qty = p.get("quantity", context.get("quantity", 1))
            sp_s = f"{sp//1_000_000} میلیون" if sp else "نامشخص"
            pr_s = f"{pr//1_000_000} میلیون" if pr and pr >= 100000 else f"{pr}"
            lines.append(f"• {p.get('model')}: فروش سالم ~{sp_s}، سود ~{pr_s}، تعداد {qty}")
        if context.get("conditions"):
            lines.append(f"\nشرایط: {', '.join(context.get('conditions',[]))}")
        if context.get("quantity"):
            lines.append(f"تعداد کل: {context.get('quantity')} تا هر مدل")
        lines.append("\nدرسته؟ اگه اوکیه بگو «اوکی» تا ست کنم، اگه چیزی جا مونده بگو تا اضافه کنم 🙏")
        return "\n".join(lines)
    if step == "done":
        return _pick(FINAL_OK)
    return "بگو ببینم، چی مد نظرته؟ 😊"


class HunterAIWizard:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state: Dict[str, Any] = {
            "step": "greeting",
            "products": [],
            "current_idx": 0,
            "messages": [],
            "raw_goal": "",
            "done": False,
            "conditions": [],
            "quantity": 1,
        }

    def get_state(self) -> Dict[str, Any]:
        return dict(self.state)

    def set_state(self, s: Dict[str, Any]):
        self.state = dict(s)

    def _current_product(self) -> Optional[Dict[str, Any]]:
        idx = self.state.get("current_idx", 0)
        prods = self.state.get("products", [])
        if 0 <= idx < len(prods):
            return prods[idx]
        return None

    def start(self) -> Dict[str, Any]:
        self.reset()
        msg = generate_ai_message("greeting", {})
        self.state["messages"].append({"role": "assistant", "text": msg})
        return {
            "reply": msg,
            "messages": list(self.state["messages"]),
            "state": self.get_state(),
            "products": [],
            "config": self.build_config(),
            "ready": False,
            "done": False,
            "step": self.state["step"],
        }

    def handle_user(self, user_text: str) -> Dict[str, Any]:
        user_text = (user_text or "").strip()
        if not user_text:
            return {
                "reply": "یه چیزی بنویس تا بفهمم چی می‌خوای 😊",
                "messages": list(self.state["messages"]),
                "state": self.get_state(),
                "ready": False,
                "config": self.build_config(),
                "step": self.state.get("step"),
                "done": bool(self.state.get("done")),
                "products": self.state.get("products", []),
            }

        self.state["messages"].append({"role": "user", "text": user_text})
        step = self.state.get("step", "greeting")

        def _finalize(reply_text: str, ready=False, extra=None):
            self.state["messages"].append({"role": "assistant", "text": reply_text})
            out = {
                "reply": reply_text,
                "messages": list(self.state["messages"]),
                "state": self.get_state(),
                "products": self.state.get("products", []),
                "config": self.build_config(),
                "ready": ready or bool(self.state.get("done")),
                "done": bool(self.state.get("done")),
                "step": self.state.get("step", step),
            }
            if extra:
                out.update(extra)
            return out

        # اگر هنوز محصول نداریم، استخراج کن
        if not self.state["products"]:
            prods = extract_products_from_text(user_text)
            if prods:
                self.state["products"] = prods
                self.state["raw_goal"] = user_text
                # تلاش برای استخراج تعداد و شرایط از همان پیام اول
                q = extract_quantity(user_text)
                if q:
                    self.state["quantity"] = q
                conds = extract_conditions(user_text)
                if conds:
                    self.state["conditions"] = conds
                self.state["step"] = "ask_sell_price"
                self.state["current_idx"] = 0
                cur = self._current_product()
                reply = generate_ai_message("ask_sell_price", {"model": cur["model"] if cur else "این دستگاه", "last_user": user_text})
                return _finalize(reply, ready=False)

        if step == "greeting" or step == "ask_products":
            prods = extract_products_from_text(user_text)
            if prods:
                existing = {p["model"] for p in self.state["products"]}
                for p in prods:
                    if p["model"] not in existing:
                        self.state["products"].append(p)
            if self.state["products"]:
                self.state["step"] = "ask_sell_price"
                cur = self._current_product()
                reply = generate_ai_message("ask_sell_price", {"model": cur["model"] if cur else "دستگاه", "last_user": user_text})
                return _finalize(reply, ready=False)
            else:
                reply = generate_ai_message("ask_products", {"last_user": user_text})
                return _finalize(reply, ready=False)

        if step == "ask_sell_price":
            cur = self._current_product()
            if cur:
                price = _parse_price_to_toman(user_text)
                if price and price >= 1_000_000:
                    cur["sell_price"] = price
                    self.state["step"] = "ask_profit"
                    reply = generate_ai_message("ask_profit", {"model": cur["model"], "sell_price": price})
                    return _finalize(reply, ready=False)
                else:
                    nums = extract_numbers(user_text)
                    if nums and max(nums) >= 1_000_000:
                        cur["sell_price"] = max(nums)
                        self.state["step"] = "ask_profit"
                        reply = generate_ai_message("ask_profit", {"model": cur["model"], "sell_price": cur["sell_price"]})
                        return _finalize(reply, ready=False)
                    reply = f"قیمت {cur['model']} رو متوجه نشدم 😅 مثلا بگو 40 میلیون یا 35 میلیون. چقدر می‌تونی سالم بفروشیش؟"
                    return _finalize(reply, ready=False)

        if step == "ask_profit":
            cur = self._current_product()
            if cur:
                profit_val = None
                is_percent = False
                m = re.search(r"(\d+)\s*(درصد|%|percent)", user_text, re.I)
                if m:
                    try:
                        profit_val = float(m.group(1))
                        is_percent = True
                    except:
                        pass
                if profit_val is None:
                    price = _parse_price_to_toman(user_text)
                    if price:
                        profit_val = price
                if profit_val is None:
                    nums = re.findall(r"\d+", user_text)
                    if nums:
                        try:
                            v = float(nums[0])
                            if v < 100 and ("درصد" in user_text or "%" in user_text or v <= 30):
                                profit_val = v
                                is_percent = True
                            else:
                                profit_val = _parse_price_to_toman(nums[0]) or int(v * 1_000_000 if v < 1000 else v)
                        except:
                            pass

                if profit_val:
                    if is_percent:
                        sp = cur.get("sell_price") or 0
                        if sp:
                            cur["profit"] = int(sp * profit_val / 100)
                            cur["profit_percent"] = profit_val
                        else:
                            cur["profit_percent"] = profit_val
                            cur["profit"] = 0
                    else:
                        cur["profit"] = int(profit_val)
                    idx = self.state["current_idx"]
                    if idx + 1 < len(self.state["products"]):
                        self.state["current_idx"] += 1
                        self.state["step"] = "ask_sell_price"
                        nxt = self._current_product()
                        reply = f"عالیه! {cur['model']} ثبت شد ✅ (سود {profit_val}{'%' if is_percent else ''}) حالا بریم سراغ {nxt['model'] if nxt else 'بعدی'}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"] if nxt else "بعدی"})
                        return _finalize(reply, ready=False)
                    else:
                        # همه سودها ثبت شد -> برو تعداد
                        self.state["step"] = "ask_quantity"
                        reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                        return _finalize(reply, ready=False)
                else:
                    reply = f"سود {cur['model']} رو متوجه نشدم 😅 مثلا بگو 3 میلیون یا 10 درصد. چقدر سود می‌خوای؟"
                    return _finalize(reply, ready=False)

        if step == "ask_quantity":
            q = extract_quantity(user_text)
            if q:
                self.state["quantity"] = q
                for p in self.state["products"]:
                    p["quantity"] = q
                self.state["step"] = "ask_conditions"
                reply = generate_ai_message("ask_conditions", {})
                return _finalize(reply, ready=False)
            else:
                # اگر عدد تنها داد
                m = re.search(r"\b(\d{1,3})\b", user_text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 1 <= v <= 100:
                            self.state["quantity"] = v
                            for p in self.state["products"]:
                                p["quantity"] = v
                            self.state["step"] = "ask_conditions"
                            reply = generate_ai_message("ask_conditions", {})
                            return _finalize(reply, ready=False)
                    except:
                        pass
                reply = "تعداد رو متوجه نشدم 😅 مثلا بگو 5 تا، یا هر مدل 3 تا. چند تا می‌خوای؟"
                return _finalize(reply, ready=False)

        if step == "ask_conditions":
            # اگر کاربر گفت "مهم نیست" یا "فرقی نداره"
            if any(w in normalize(user_text) for w in ["مهم نیست", "فرقی نداره", "هرچی", "نداره", "رد شو"]):
                self.state["conditions"] = []
                self.state["step"] = "confirm"
                reply = generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                return _finalize(reply, ready=False)
            conds = extract_conditions(user_text)
            if conds or len(user_text) < 50:
                # اگر چیزی استخراج شد یا متن کوتاه بود، ذخیره کن
                if conds:
                    self.state["conditions"] = conds
                else:
                    # متن کوتاه بدون قیمت را به عنوان شرط بگیر
                    if "میلیون" not in user_text and "سود" not in user_text:
                        self.state["conditions"] = [user_text[:60]]
                self.state["step"] = "confirm"
                reply = generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                return _finalize(reply, ready=False)
            else:
                self.state["conditions"] = [user_text[:80]]
                self.state["step"] = "confirm"
                reply = generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                return _finalize(reply, ready=False)

        if step == "confirm":
            if any(w in normalize(user_text) for w in ["اوکی", "ok", "باشه", "درسته", "آره", "ست کن", "تایید"]):
                self.state["step"] = "done"
                self.state["done"] = True
                reply = generate_ai_message("done", {"products": self.state["products"]})
                cfg = self.build_config()
                return _finalize(reply, ready=True, extra={"config": cfg})
            else:
                new_prods = extract_products_from_text(user_text)
                if new_prods:
                    existing = {p["model"] for p in self.state["products"]}
                    for p in new_prods:
                        if p["model"] not in existing:
                            self.state["products"].append(p)
                    reply = "اضافه کردم ✅\n\n" + generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                    return _finalize(reply, ready=False)
                q = extract_quantity(user_text)
                if q:
                    self.state["quantity"] = q
                    for p in self.state["products"]:
                        p["quantity"] = q
                    reply = "تعداد اصلاح شد 👍\n\n" + generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                    return _finalize(reply, ready=False)
                conds = extract_conditions(user_text)
                if conds:
                    self.state["conditions"] = conds
                    reply = "شرایط اصلاح شد 👍\n\n" + generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                    return _finalize(reply, ready=False)
                price = _parse_price_to_toman(user_text)
                if price:
                    cur = self.state["products"][-1] if self.state["products"] else None
                    if cur:
                        if not cur.get("profit"):
                            cur["profit"] = price
                        else:
                            cur["sell_price"] = price
                        reply = "اوکی، اصلاح شد 👍\n\n" + generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                        return _finalize(reply, ready=False)
                reply = generate_ai_message("confirm", {"products": self.state["products"], "quantity": self.state["quantity"], "conditions": self.state["conditions"]})
                return _finalize(reply, ready=False)

        if step == "done":
            cfg = self.build_config()
            reply = generate_ai_message("done", {"products": self.state["products"]})
            return _finalize(reply, ready=True, extra={"config": cfg})

        reply = "بگو ببینم، دنبال چه دستگاهایی هستی؟ مثلا آیفون 12 13 14 15؟"
        return _finalize(reply, ready=False)

    def build_config(self) -> Dict[str, Any]:
        keywords = []
        hunter_adv_by_keyword = {}
        warnings = []
        for p in self.state["products"]:
            model = p.get("model") or p.get("keyword") or "دستگاه"
            sell_price = int(p.get("sell_price") or 0)
            profit = int(p.get("profit") or 0)
            profit_percent = float(p.get("profit_percent") or 0)
            if profit_percent and not profit:
                if sell_price:
                    profit = int(sell_price * profit_percent / 100)
            buy_target = sell_price - profit if sell_price and profit else 0
            if buy_target <= 0 and sell_price:
                buy_target = int(sell_price * 0.85)
            if sell_price and profit:
                pct = profit / sell_price * 100
                good_pct = max(8, min(25, pct * 0.8))
                great_pct = max(12, min(35, pct * 1.2))
            else:
                good_pct = 10
                great_pct = 20
            adv = {
                "good_pct": round(good_pct, 1),
                "great_pct": round(great_pct, 1),
                "suspicious_pct": 50,
                "dealer_mode": False,
                "sell_price": sell_price,
                "profit": profit,
                "profit_percent": profit_percent,
                "buy_target": buy_target,
                "quantity": p.get("quantity", self.state.get("quantity", 1)),
                "model": model,
                "conditions": self.state.get("conditions", []),
            }
            price_min = int(buy_target * 0.5) if buy_target else 0
            price_max = int(buy_target * 1.1) if buy_target else 0
            keywords.append({
                "keyword": model,
                "category": p.get("category") or "mobile-phones",
                "price_min": price_min,
                "price_max": price_max,
                "hunter": True,
                "vip": True,
                "hunter_adv": adv,
                "sell_price": sell_price,
                "profit": profit,
                "buy_target": buy_target,
            })
            hunter_adv_by_keyword[model] = adv
            if sell_price and profit and profit > sell_price * 0.3:
                warnings.append(f"{model}: سود {profit//1_000_000}م روی فروش {sell_price//1_000_000}م خیلی بالاست")

        items = []
        for k in keywords:
            items.append({
                "model": k["keyword"],
                "keyword": k["keyword"],
                "category": k["category"],
                "healthy_sell_price": k["sell_price"],
                "desired_profit": k["profit"],
                "max_buy": k["buy_target"],
                "price_min": k["price_min"],
                "price_max": k["price_max"],
                "hunter_adv": k["hunter_adv"],
                "conditions": self.state.get("conditions", []),
            })

        return {
            "products": self.state["products"],
            "keywords": keywords,
            "items": items,
            "hunter_adv": hunter_adv_by_keyword,
            "warnings": warnings,
            "summary": f"{len(keywords)} مدل تنظیم شد — سود متوسط {(sum(k['profit'] for k in keywords)//len(keywords)//1_000_000) if keywords else 0} میلیون" if keywords else "هنوز مدلی ثبت نشده",
            "created_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "state": self.state.get("step"),
            "quantity": self.state.get("quantity", 1),
            "conditions": self.state.get("conditions", []),
        }


_wizard_sessions: Dict[str, HunterAIWizard] = {}


def get_wizard(session_id: str) -> HunterAIWizard:
    if session_id not in _wizard_sessions:
        _wizard_sessions[session_id] = HunterAIWizard()
    return _wizard_sessions[session_id]
