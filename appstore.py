"""StoreKit AppTransaction 驗證。

只接受 Apple 簽署且 bundle / environment 驗證通過的 JWS。呼叫端只會拿到
appTransactionID，不會把原始 JWS 或 Apple ID 寫進資料庫。
"""
import base64
import json
import os
from functools import lru_cache
from pathlib import Path

from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException


class AppTransactionError(ValueError):
    pass


def _decode_payload_without_trust(jws: str) -> dict:
    """只用於選擇驗證環境；所有欄位仍須經 SignedDataVerifier 驗證。"""
    try:
        payload = jws.split(".")[1]
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        return json.loads(raw)
    except Exception as exc:
        raise AppTransactionError("invalid_jws") from exc


@lru_cache(maxsize=2)
def _verifier(environment: str) -> SignedDataVerifier:
    env = Environment.PRODUCTION if environment == "Production" else Environment.SANDBOX
    cert_dir = Path(os.environ.get("APPLE_ROOT_CERT_DIR", Path(__file__).parent / "certs"))
    roots = [p.read_bytes() for p in sorted(cert_dir.glob("AppleRootCA-G*.pem"))]
    if not roots:
        raise AppTransactionError("missing_apple_root_certificates")
    app_id_raw = os.environ.get("APPLE_APP_ID", "").strip()
    if env == Environment.PRODUCTION and not app_id_raw:
        raise AppTransactionError("missing_apple_app_id")
    try:
        app_id = int(app_id_raw) if app_id_raw else None
    except ValueError as exc:
        raise AppTransactionError("invalid_apple_app_id") from exc
    return SignedDataVerifier(
        roots,
        True,
        env,
        os.environ.get("APPLE_BUNDLE_ID", "com.hexagram.app"),
        app_id,
    )


def verify_app_transaction(jws: str) -> str:
    if not isinstance(jws, str) or len(jws) > 20000:
        raise AppTransactionError("invalid_jws")
    untrusted = _decode_payload_without_trust(jws)
    environment = untrusted.get("environment")
    if environment not in ("Production", "Sandbox"):
        raise AppTransactionError("unsupported_environment")
    try:
        payload = _verifier(environment).verify_and_decode_app_transaction(jws)
    except VerificationException as exc:
        raise AppTransactionError("verification_failed") from exc
    identifier = getattr(payload, "appTransactionId", None)
    if not identifier:
        raise AppTransactionError("missing_app_transaction_id")
    return str(identifier)
