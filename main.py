"""
九江学院图书馆座位预约脚本（纯 requests 版）
基于 ChaoXingReserveSeat 项目适配，纯 Python 实现 enc 签名，无需浏览器
支持验证码自动识别（ddddocr）
"""
import json
import re
import time
import base64
import datetime
import argparse
import os
import sys
import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from utils import aes_encrypt, calc_enc, extract_submit_enc

urllib3.disable_warnings(InsecureRequestWarning)

# 全局 OCR 实例（懒加载）
_ocr = None

def _get_ocr():
    global _ocr
    if _ocr is None:
        import ddddocr
        _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr

# ==================== 可配置参数 ====================
SLEEPTIME = 0.3          # 每次重试间隔（秒）
ENDTIME = "21:35:00"     # 停止尝试时间（放号时间 + 5分钟）
MAX_ATTEMPT = 10         # 最大尝试次数
RESERVE_DAYS_AHEAD = 1   # 预约几天后的座位（1=明天）
# ===================================================


class SeatReserver:
    """座位预约器"""

    def __init__(self, dept_id_enc: str):
        self.dept_id_enc = dept_id_enc
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.select_url = ("https://office.chaoxing.com/front/third/apps/seat/select"
                           f"?deptIdEnc={dept_id_enc}&id={{room_id}}&day={{day}}"
                           f"&backLevel=2&fidEnc={dept_id_enc}")
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.captcha_url = "https://office.chaoxing.com/data/apps/seat/captcha"
        self.session = requests.Session()
        self.ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) "
                   "AppleWebKit/603.1.3 (KHTML, like Gecko) Version/10.0 Mobile/14E304 "
                   "Safari/602.1 wechatdevtools/1.05.2109131 MicroMessenger/8.0.5 "
                   "Language/zh_CN webview/16364215743155638")
        self.session.headers.update({
            "User-Agent": self.ua,
            "X-Requested-With": "com.tencent.mm",
        })

    def login(self, username: str, password: str) -> bool:
        """用户名密码登录（AES 加密）"""
        # 先访问登录页获取 cookie
        self.session.get(url=self.login_page, verify=False)

        # 加密用户名密码
        enc_username = aes_encrypt(username)
        enc_password = aes_encrypt(password)

        parm = {
            "fid": -1,
            "uname": enc_username,
            "password": enc_password,
            "refer": ("http%3A%2F%2Foffice.chaoxing.com%2Ffront%2Fthird%2Fapps"
                      "%2Fseat%2Fcode%3Fid%3D4219%26seatNum%3D380"),
            "t": True
        }
        self.session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "passport2.chaoxing.com"
        })
        resp = self.session.post(url=self.login_url, params=parm, verify=False)
        obj = resp.json()
        if obj.get("status"):
            print(f"  [登录成功] {username}")
            self.session.headers.pop("Host", None)
            self.session.headers.pop("Content-Type", None)
            return True
        else:
            print(f"  [登录失败] {obj.get('msg2', '未知错误')}")
            return False

    def load_cookies(self, cookie_file: str) -> bool:
        """从 JSON 文件加载 cookie（替代用户名密码登录）"""
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            for c in state.get("cookies", []):
                self.session.cookies.set(
                    c["name"], c["value"], domain=c["domain"], path=c.get("path", "/")
                )
            print(f"  [Cookie 加载成功] 共 {len(state.get('cookies', []))} 个")
            return True
        except Exception as e:
            print(f"  [Cookie 加载失败] {e}")
            return False

    def get_submit_enc(self, room_id: int, day: str) -> str:
        """访问选座页面，提取 submit_enc 值"""
        url = self.select_url.format(room_id=room_id, day=day)
        resp = self.session.get(url, verify=False)
        if resp.status_code != 200:
            return ""
        return extract_submit_enc(resp.text)

    def get_captcha(self) -> str:
        """获取验证码图片并用 ddddocr 识别

        Returns:
            识别出的验证码字符串，失败返回空字符串
        """
        try:
            resp = self.session.get(self.captcha_url, verify=False)
            data = resp.json()
            if not data.get("success"):
                return ""
            img_data = data["data"]["captchaUrl"]
            # 处理 data:image/jpeg;base64,xxx 格式
            if "," in img_data:
                img_base64 = img_data.split(",", 1)[1]
            else:
                img_base64 = img_data
            img_bytes = base64.b64decode(img_base64)
            ocr = _get_ocr()
            result = ocr.classification(img_bytes)
            return result.strip()
        except Exception as e:
            print(f"    [验证码获取失败] {e}")
            return ""

    def reserve(self, room_id: int, day: str, start_time: str,
                end_time: str, seat_num: str, use_captcha: bool = True,
                captcha_retries: int = 3) -> dict:
        """执行一次预约（含验证码自动识别与重试）

        Args:
            use_captcha: 是否获取并提交验证码
            captcha_retries: 验证码错误时的重试次数

        Returns:
            {"success": bool, "msg": str}
        """
        captcha = ""
        for attempt in range(captcha_retries + 1):
            # 1. 获取 submit_enc
            submit_enc = self.get_submit_enc(room_id, day)
            if not submit_enc:
                return {"success": False, "msg": "获取 submit_enc 失败"}

            # 2. 获取验证码（如需）
            if use_captcha:
                captcha = self.get_captcha()
                if captcha:
                    print(f"    [验证码] 识别结果: {captcha}")
                else:
                    print(f"    [验证码] 获取失败，使用空值")

            # 3. 计算 enc 签名（captcha 参与签名）
            param_obj = {
                "deptIdEnc": self.dept_id_enc,
                "roomId": room_id,
                "day": day,
                "startTime": start_time,
                "endTime": end_time,
                "seatNum": seat_num,
                "captcha": captcha,
                "wyToken": ""
            }
            enc = calc_enc(param_obj, submit_enc)

            # 4. 提交预约
            self.session.headers.update({
                "Referer": self.select_url.format(room_id=room_id, day=day),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01"
            })
            parm = {
                "deptIdEnc": self.dept_id_enc,
                "roomId": room_id,
                "startTime": start_time,
                "endTime": end_time,
                "day": day,
                "seatNum": seat_num,
                "captcha": captcha,
                "wyToken": "",
                "enc": enc
            }
            resp = self.session.post(self.submit_url, params=parm, verify=False)
            try:
                result = resp.json()
            except Exception:
                return {"success": False, "msg": f"响应解析失败: {resp.text[:200]}"}

            msg = result.get("msg", "")
            success = result.get("success", False)

            # 验证码错误则重试
            if not success and use_captcha and ("验证码" in msg or "captcha" in msg.lower()):
                print(f"    [验证码错误] {msg}，重试 ({attempt+1}/{captcha_retries})...")
                time.sleep(0.2)
                continue

            return {"success": success, "msg": msg}

        return {"success": False, "msg": "验证码重试次数耗尽"}

    def find_any_seat(self, room_id: int, day: str, start_time: str,
                       end_time: str, max_seat: int = 800,
                       use_captcha: bool = True) -> str:
        """ brute-force 查找当前房间任意可用座位

        Returns:
            座位号字符串（如 "036"），找不到返回空字符串
        """
        print("    随机查找可用座位...")
        for seat_num in range(1, max_seat + 1):
            seat_str = str(seat_num).zfill(3)
            result = self.reserve(
                room_id=room_id, day=day,
                start_time=start_time, end_time=end_time,
                seat_num=seat_str, use_captcha=use_captcha
            )
            if result["success"]:
                print(f"    找到可用座位: {seat_str}")
                return seat_str
            # 座位被约/不可用就继续，不打印每个失败
            time.sleep(0.05)
        return ""


def get_target_day() -> str:
    """获取目标日期（明天）"""
    target = datetime.date.today() + datetime.timedelta(days=RESERVE_DAYS_AHEAD)
    return target.strftime("%Y-%m-%d")


def get_beijing_time() -> str:
    """获取北京时间字符串"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    beijing = utc_now + datetime.timedelta(hours=8)
    return beijing.strftime("%H:%M:%S")


def wait_until(target_time: str):
    """等待到目标时间（北京时间）"""
    print(f"等待到 {target_time}...")
    while True:
        current = get_beijing_time()
        if current >= target_time:
            print(f"到达目标时间 {current}")
            return
        # 最后 10 秒高频检查
        remaining = _seconds_until(target_time)
        if remaining > 10:
            time.sleep(min(5, remaining - 10))
        else:
            time.sleep(0.05)


def _seconds_until(target_time: str) -> float:
    """计算距离目标时间还有多少秒"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    beijing = utc_now + datetime.timedelta(hours=8)
    h, m, s = map(int, target_time.split(":"))
    target = beijing.replace(hour=h, minute=m, second=s, microsecond=0)
    if target < beijing:
        target += datetime.timedelta(days=1)
    return (target - beijing).total_seconds()


def run_reserve(config: dict, username: str = None, password: str = None,
                cookie_file: str = None, day: str = None):
    """执行预约主流程"""
    dept_id_enc = config.get("deptIdEnc", "")
    rooms = config.get("rooms", [])
    seats = config.get("seats", [])
    # 三段式全天预约：按优先级排列，第一个为必选段（失败换下一个座位），其余为可选段（失败跳过）
    segments = config.get("segments", config.get("timeSlots", []))
    use_captcha = config.get("useCaptcha", True)

    if day is None:
        day = get_target_day()

    print(f"目标日期: {day}")
    print(f"房间列表: {[r['name'] for r in rooms]}")
    print(f"座位列表: {seats}")
    print(f"时段列表: {[(s.get('name',''), s['start'], s['end']) for s in segments]}")
    print(f"验证码识别: {'开启' if use_captcha else '关闭'}")

    reserver = SeatReserver(dept_id_enc)

    # 登录
    print("\n[登录]")
    if cookie_file and os.path.exists(cookie_file):
        if not reserver.load_cookies(cookie_file):
            return False
    elif username and password:
        if not reserver.login(username, password):
            return False
    else:
        print("  错误：未提供登录信息（用户名密码或 cookie 文件）")
        return False

    if not segments:
        print("  错误：配置中没有时段（segments）")
        return False

    # 三段式全天预约逻辑
    # 第一个时段为必选段（下午），失败则换下一个座位
    # 其余时段为可选段（晚上、早上），失败则跳过该时段
    required_seg = segments[0]
    optional_segs = segments[1:]

    for room in rooms:
        print(f"\n{'='*50}")
        print(f"房间: {room['name']} (id={room['id']})")
        print(f"{'='*50}")

        # 第一轮：尝试备选座位
        for seat in seats:
            seat_str = str(seat).zfill(3)
            print(f"\n[座位 {seat_str}]")

            # 必选段（下午）——失败则换下一个座位
            print(f"  必选段 [{required_seg.get('name','')}] "
                  f"{required_seg['start']}-{required_seg['end']}")
            result = reserver.reserve(
                room_id=room["id"], day=day,
                start_time=required_seg["start"], end_time=required_seg["end"],
                seat_num=seat_str, use_captcha=use_captcha
            )
            print(f"    结果: {result['msg']}")
            if not result["success"]:
                print(f"    必选段失败，换下一个座位")
                continue

            booked = [required_seg.get("name", required_seg["start"])]

            # 可选段（晚上、早上）——失败跳过
            for seg in optional_segs:
                print(f"  可选段 [{seg.get('name','')}] {seg['start']}-{seg['end']}")
                result = reserver.reserve(
                    room_id=room["id"], day=day,
                    start_time=seg["start"], end_time=seg["end"],
                    seat_num=seat_str, use_captcha=use_captcha
                )
                print(f"    结果: {result['msg']}")
                if result["success"]:
                    booked.append(seg.get("name", seg["start"]))
                else:
                    print(f"    跳过该时段")
                time.sleep(SLEEPTIME)

            print(f"\n{'='*50}")
            print(f"预约完成！{room['name']} 座位{seat_str} {day}")
            print(f"已约时段: {'、'.join(booked)}")
            print(f"{'='*50}")
            return True

        # 第二轮：备选座位全部失败，随机找一个当前房间可用座位
        print(f"\n[备选座位全部失败，随机查找可用座位]")
        any_seat = reserver.find_any_seat(
            room_id=room["id"], day=day,
            start_time=required_seg["start"], end_time=required_seg["end"],
            use_captcha=use_captcha
        )
        if any_seat:
            booked = [required_seg.get("name", required_seg["start"])]
            for seg in optional_segs:
                print(f"  可选段 [{seg.get('name','')}] {seg['start']}-{seg['end']}")
                result = reserver.reserve(
                    room_id=room["id"], day=day,
                    start_time=seg["start"], end_time=seg["end"],
                    seat_num=any_seat, use_captcha=use_captcha
                )
                print(f"    结果: {result['msg']}")
                if result["success"]:
                    booked.append(seg.get("name", seg["start"]))
                time.sleep(SLEEPTIME)

            print(f"\n{'='*50}")
            print(f"预约完成（随机座位）！{room['name']} 座位{any_seat} {day}")
            print(f"已约时段: {'、'.join(booked)}")
            print(f"{'='*50}")
            return True

        print(f"  房间 {room['name']} 无可用座位，尝试下一个房间")

    print(f"\n所有房间均无可用座位")
    return False


def main():
    parser = argparse.ArgumentParser(description="九江学院图书馆座位预约脚本")
    parser.add_argument("-c", "--config", default="config.json", help="配置文件路径")
    parser.add_argument("-m", "--mode", default="reserve",
                        choices=["reserve", "debug", "now"],
                        help="reserve=等到点执行, debug=立即测试, now=立即执行")
    parser.add_argument("-d", "--day", default=None, help="指定预约日期 YYYY-MM-DD")
    parser.add_argument("-u", "--username", default=None, help="学习通账号")
    parser.add_argument("-p", "--password", default=None, help="学习通密码")
    parser.add_argument("--cookie", default=None, help="cookie 文件路径（storage_state.json）")
    args = parser.parse_args()

    # 加载配置
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 从环境变量获取账号密码（GitHub Actions 用）
    username = args.username or os.environ.get("USERNAME", "")
    password = args.password or os.environ.get("PASSWORD", "")
    cookie_file = args.cookie or os.environ.get("COOKIE_FILE", "")

    print("=" * 50)
    print("九江学院图书馆座位预约脚本")
    print(f"当前北京时间: {get_beijing_time()}")
    print("=" * 50)

    if args.mode == "reserve":
        # 等到 21:30 执行
        wait_until("21:30:00")

    success = run_reserve(
        config, username=username, password=password,
        cookie_file=cookie_file, day=args.day
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
