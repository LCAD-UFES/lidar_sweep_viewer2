# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# google-cloud-storage and google-auth ship no type information; their results are cast at this boundary and nowhere else.
import os, warnings
from typing import BinaryIO, cast, override
warnings.filterwarnings("ignore", module=r"google\.")   # user ADC carries no quota project; harmless for reads
from google.auth import load_credentials_from_file
from google.cloud import storage
from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
import pyarrow.parquet as pq
from .base import Source
from ..config import LASERS_PER_FRAME

FOLDERS = ("training", "validation", "testing")   # where the bucket keeps the file; not a dataset split (DESIGN.md)

class GcsSource(Source):
    # credentials: path to an ADC json (gcloud auth application-default login) or a service-account json
    def __init__(self, credentials: str, bucket: str = "waymo_open_dataset_v_2_0_1", component: str = "lidar") -> None:
        creds, _ = load_credentials_from_file(credentials)
        self.bucket: Bucket = storage.Client(project="lsv2", credentials=creds).bucket(bucket)   # project is a placeholder: user ADC has none
        self.component: str = component

    @override
    def resolve(self, sid: str) -> tuple[str, int]:
        for folder in FOLDERS:
            blob = self.bucket.get_blob(f"{folder}/{self.component}/{sid}.parquet")
            if blob is not None: return f"gs://{self.bucket.name}/{cast(str, blob.name)}", cast(int, blob.size)
        raise FileNotFoundError(f"{sid}: no {self.component} parquet under {FOLDERS} in gs://{self.bucket.name}")

    def _blob(self, obj: str) -> Blob: return self.bucket.blob(obj.removeprefix(f"gs://{self.bucket.name}/"))

    @override
    def fetch(self, obj: str, dst: str) -> None:
        self._blob(obj).download_to_filename(dst + ".part")
        os.replace(dst + ".part", dst)

    @override
    def frames(self, obj: str) -> int | None:
        # only the parquet footer is transferred; every frame has one row per laser
        with cast(BinaryIO, cast(object, self._blob(obj).open("rb"))) as f: return pq.ParquetFile(f).metadata.num_rows // LASERS_PER_FRAME
