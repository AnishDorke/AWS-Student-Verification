import json
import boto3
import os
import re
import base64
import hmac
import hashlib
import time
import uuid

s3 = boto3.client("s3")

BUCKET_NAME = "college-id-verification-anish-2026"
UPLOAD_PREFIX = "uploads/"
MAX_FILE_SIZE = 5 * 1024 * 1024

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg"
}


def lambda_handler(event, context):
    try:
        if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
            return response(200, {"message": "CORS preflight"})

        body = event.get("body") or "{}"

        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")

        data = json.loads(body)


        expected_code = os.environ.get("DEMO_ACCESS_CODE")
        provided_code = data.get("accessCode")

        if not expected_code:
            return response(500, {
                "error": "Demo access code is not configured"
            })

        if not isinstance(provided_code, str) or provided_code != expected_code:
            return response(401, {
                "error": "Invalid demo access code"
            })


        filename = os.path.basename(str(data.get("filename", "")))
        content_type = str(data.get("contentType", "")).lower()
        file_size = data.get("fileSize")

        if not filename or filename in (".", ".."):
            return response(400, {"error": "A valid filename is required"})

        if not isinstance(file_size, int) or isinstance(file_size, bool):
            return response(400, {"error": "Invalid file size"})

        if file_size <= 0:
            return response(400, {"error": "Empty files are not allowed"})

        if file_size > MAX_FILE_SIZE:
            return response(400, {"error": "File exceeds the 5 MiB limit"})

        extension = os.path.splitext(filename)[1].lower()

        if extension not in ALLOWED_TYPES:
            return response(400, {"error": "Unsupported file format"})

        expected_type = ALLOWED_TYPES[extension]

        if content_type != expected_type:
            return response(400, {"error": "File extension and content type do not match"})

        object_key = f"{UPLOAD_PREFIX}{uuid.uuid4()}{extension}"

        fields = {
            "Content-Type": expected_type,
            "success_action_status": "201"
        }

        conditions = [
            {"Content-Type": expected_type},
            {"success_action_status": "201"},
            ["content-length-range", 1, MAX_FILE_SIZE],
            ["starts-with", "$key", UPLOAD_PREFIX]
        ]

        presigned_post = s3.generate_presigned_post(
            Bucket=BUCKET_NAME,
            Key=object_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=60
        )

        return response(200, {
            "upload": presigned_post,
            "key": object_key,
            "expiresInSeconds": 60,
            "maxFileSizeBytes": MAX_FILE_SIZE
        })

    except Exception as e:
        print(f"UPLOAD AUTHORIZATION ERROR: {type(e).__name__}: {str(e)}")
        return response(500, {"error": "Unable to authorize upload"})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store"
        },
        "body": json.dumps(body)
    }
