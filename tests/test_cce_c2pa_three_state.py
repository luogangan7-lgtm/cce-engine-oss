#!/usr/bin/env python3
"""C2PA 三态: present / absent / not_available —— 三条分支都在**真实输入**上验过。

## 为什么值得单独一条测试
`absent` 的意思是「查过、确实没有」; `not_available` 的意思是「查不了, 不知道」。
把后者写成前者, 是本项目记过的事故模式(2026-09-03 我就在这个文件里硬编码过 `absent`)。
接上官方 c2pa 库(0.37.8)之后, 这三态才真的可分, 所以三条分支都得有实证:

  present       ← **现场签一张真图**(自建两级证书链), 读得出 manifest
  absent        ← 未签名的真 PNG, 库明确报 ManifestNotFound
  not_available ← 非图片文件 / 库缺席

★ 只验 absent 不验 present, 等于没验「三态可分」—— 一个恒返回 absent 的实现也能过。

## 不 skip
缺 c2pa/cryptography **直接红**。理由同 test_cce_image_chain_ci: 一 skip,
「C2PA 真解析」就只是名义上做了, 而失效时无声。
"""
import datetime, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import c2pa
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
except Exception as e:                                        # noqa: BLE001
    raise SystemExit(f"★ 缺依赖({e}) —— 本测试**不 skip**: 一 skip,「C2PA 真解析」就只是名义上做了。"
                     "装: pip install -r requirements-media.txt")

import cce_image_ingest as II
import cce_synth_image as SI


def _chain():
    """两级链: 根 CA 签叶证书。c2pa 硬拒自签名, 所以必须是两级。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CCE CI Root CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(days=1))
          .not_valid_after(now + datetime.timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True,
                                       False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                         critical=False)
          .sign(ca_key, hashes.SHA256()))
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cce-ci-signer")]))
            .issuer_name(ca_name).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=20))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False,
                                         False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION]),
                           critical=True)
            # ★ c2pa 硬要 SKI/AKI —— openssl 默认加, cryptography 不加。
            #   少了它报的是「the certificate is invalid」, 看不出缺的是哪一项。
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
                           critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                           critical=False)
            .sign(ca_key, hashes.SHA256()))
    pem = leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM)
    key = leaf_key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    return pem, key


with tempfile.TemporaryDirectory() as td:
    plain = os.path.join(td, "plain.png")
    SI.synth(plain)

    # ── absent: 真 PNG, 未签名 ⇒ 库明确说没有 ─────────────────────────
    assert II.c2pa_state(plain) == "absent", "★ 未签名的真 PNG 应判 absent(查过确无)"

    # ── present: 现场签名 ⇒ 读得出 manifest ───────────────────────────
    pem, key = _chain()
    signed = os.path.join(td, "signed.png")
    info = c2pa.C2paSignerInfo(alg=b"es256", sign_cert=pem, private_key=key, ta_url=None)
    b = c2pa.Builder({"claim_generator_info": [{"name": "cce-ci", "version": "1"}],
                      "assertions": [{"label": "c2pa.actions",
                                      "data": {"actions": [{"action": "c2pa.created"}]}}]})
    with open(plain, "rb") as s, open(signed, "wb+") as d:
        b.sign(c2pa.Signer.from_info(info), "image/png", s, d)
    assert c2pa.Reader(signed).is_embedded(), "★ 签名没嵌进去, 后面这条断言就是空的"
    assert II.c2pa_state(signed) == "present", "★ 签过名的图应判 present"

    # ── not_available: 根本不是图片 ───────────────────────────────────
    txt = os.path.join(td, "notimage.txt")
    open(txt, "w").write("这不是图片")
    assert II.c2pa_state(txt) == "not_available", \
        "★ 查不了必须记 not_available —— **不许**降成 absent"

    # ── 反向: 库缺席时, 未命中仍是 not_available 而非 absent ───────────
    import builtins
    _real = builtins.__import__
    builtins.__import__ = lambda n, *a, **k: (_ for _ in ()).throw(ImportError("强制")) \
        if n == "c2pa" else _real(n, *a, **k)
    try:
        degraded = II.c2pa_state(plain)
    finally:
        builtins.__import__ = _real
    assert degraded == "not_available", \
        f"★ 没有解析器时「找不到」不等于「没有」, 却判成了 {degraded!r}"

    # ── 三态**不得**用来推断媒体为假(2026-08-15 调研结论) ────────────
    src = open(os.path.join(ROOT, "scripts/cce_image_ingest.py"), encoding="utf-8").read()
    assert "不得据此推断媒体为假" in src, "★ 这条边界要留在代码里, 不能只在提交信息里"

print("test_cce_c2pa_three_state: OK (present=现场签真图 · absent=未签名真PNG库明确报无 · "
      "not_available=非图片 | 反向: 库缺席时未命中仍是 not_available 不降成 absent | "
      "三态都不得推断媒体为假, 边界留在代码里)")
