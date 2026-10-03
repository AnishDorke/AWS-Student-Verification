import json
import boto3
import os
import uuid
import warnings
from io import BytesIO
from urllib.parse import unquote_plus
from PIL import Image, UnidentifiedImageError

s3 = boto3.client("s3")

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_DIMENSION = 1600

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


def lambda_handler(event, context):
    try:
        record = event["Records"][0]["s3"]
        bucket = record["bucket"]["name"]
        key = unquote_plus(record["object"]["key"])

        if not key.startswith("uploads/"):
            print(f"REJECTED: Invalid upload location: {key}")
            return response(400, "Invalid upload location")

        filename = os.path.basename(key)
        extension = os.path.splitext(filename)[1].lower()

        if extension not in ALLOWED_EXTENSIONS:
            print(f"REJECTED: Unsupported file format: {filename}")
            return response(400, "Unsupported file format")

        obj = s3.get_object(Bucket=bucket, Key=key)
        file_size = obj["ContentLength"]

        if file_size > MAX_FILE_SIZE:
            print(
                f"REJECTED: File exceeds 5 MB limit: "
                f"{filename} ({file_size} bytes)"
            )
            return response(400, "File exceeds 5 MB limit")

        file_data = obj["Body"].read()

        if extension == ".pdf":
            if not file_data.startswith(b"%PDF-"):
                print(f"REJECTED: Invalid PDF file: {filename}")
                return response(400, "Invalid PDF file")

            output_key = f"processed/{uuid.uuid4()}.pdf"

            s3.put_object(
                Bucket=bucket,
                Key=output_key,
                Body=file_data,
                ContentType="application/pdf",
                ServerSideEncryption="AES256"
            )

            print(f"SUCCESS: Validated PDF stored at {output_key}")
            return response(
                200,
                f"PDF validated and stored at {output_key}"
            )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter(
                    "error",
                    Image.DecompressionBombWarning
                )

                image = Image.open(BytesIO(file_data))

                if image.format not in ("JPEG", "PNG"):
                    print(
                        f"REJECTED: File content is not JPEG or PNG: "
                        f"{filename}"
                    )
                    return response(
                        400,
                        "File content does not match an allowed image format"
                    )

                if image.width * image.height > MAX_PIXELS:
                    print(
                        f"REJECTED: Image dimensions too large: "
                        f"{filename} ({image.width}x{image.height})"
                    )
                    return response(
                        400,
                        "Image dimensions are too large"
                    )

                image.verify()

                image = Image.open(BytesIO(file_data))

                if image.width * image.height > MAX_PIXELS:
                    print(f"REJECTED: Image dimensions too large: {filename}")
                    return response(
                        400,
                        "Image dimensions are too large"
                    )

                image.thumbnail(
                    (MAX_DIMENSION, MAX_DIMENSION),
                    Image.Resampling.LANCZOS
                )

                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")

                output = BytesIO()
                image.save(output, format="PNG", optimize=True)
                output.seek(0)

        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            ValueError
        ) as e:
            print(f"REJECTED: Invalid or unsafe image {filename}: {str(e)}")
            return response(400, "Invalid or unsafe image file")

        output_key = f"processed/{uuid.uuid4()}.png"

        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=output.getvalue(),
            ContentType="image/png",
            ServerSideEncryption="AES256"
        )

        print(f"SUCCESS: Image processed and stored at {output_key}")

        return response(
            200,
            f"Image processed and stored at {output_key}"
        )

    except Exception as e:
        print(f"PROCESSING ERROR: {type(e).__name__}: {str(e)}")
        return response(500, "File processing failed")


def response(status_code, message):
    return {
        "statusCode": status_code,
        "body": json.dumps(message)
    }
