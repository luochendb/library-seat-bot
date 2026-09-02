"""enc 签名计算：纯 Python 实现，无需执行 JS

算法：
1. 对参数对象的键按字母排序
2. 拼接成 [key=value][key=value]... 格式
3. 最后拼接 [submit_enc值]
4. 对整体字符串做 MD5
"""
import hashlib


def calc_enc(param_obj: dict, submit_enc: str) -> str:
    """计算提交用的 enc 签名

    Args:
        param_obj: 参数字典，包含 deptIdEnc, roomId, day, startTime, endTime,
                   seatNum, captcha, wyToken 等
        submit_enc: 从选座页面 HTML 中提取的 submit_enc 隐藏值

    Returns:
        32 位 MD5 字符串
    """
    sorted_keys = sorted(param_obj.keys())
    concat = ""
    for key in sorted_keys:
        concat += f"[{key}={param_obj[key]}]"
    concat += f"[{submit_enc}]"
    return hashlib.md5(concat.encode('utf-8')).hexdigest()


def extract_submit_enc(html: str) -> str:
    """从选座页面 HTML 中提取 submit_enc 隐藏值"""
    import re
    match = re.search(r'submit_enc"\s+value="([^"]+)"', html)
    if not match:
        match = re.search(r'id="submit_enc"[^>]*value="([^"]+)"', html)
    return match.group(1) if match else ""
