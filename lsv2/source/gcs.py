import os, warnings
warnings.filterwarnings("ignore", module=r"google\.")   # user ADC carries no quota project; harmless for reads
from google.auth import load_credentials_from_file
from google.cloud import storage
from . import Source

FOLDERS = ("training", "validation", "testing")   # where the bucket keeps the file; not a dataset split (DESIGN.md)

class GcsSource(Source):
    # credentials: path to an ADC json (gcloud auth application-default login) or a service-account json
    def __init__(self, credentials, bucket="waymo_open_dataset_v_2_0_1", component="lidar"):
        creds, _ = load_credentials_from_file(credentials)
        self.bucket = storage.Client(project="lsv2", credentials=creds).bucket(bucket)   # project is a placeholder: user ADC has none
        self.component = component

    def resolve(self, sid):
        for folder in FOLDERS:
            blob = self.bucket.get_blob(f"{folder}/{self.component}/{sid}.parquet")
            if blob: return f"gs://{self.bucket.name}/{blob.name}", blob.size
        raise FileNotFoundError(f"{sid}: no {self.component} parquet under {FOLDERS} in gs://{self.bucket.name}")

    def _blob(self, obj): return self.bucket.blob(obj.removeprefix(f"gs://{self.bucket.name}/"))

    def fetch(self, obj, dst):
        self._blob(obj).download_to_filename(dst + ".part")
        os.replace(dst + ".part", dst)

    def frames(self, obj):
        # only the parquet footer is transferred; every frame has one row per laser
        import pyarrow.parquet as pq
        from ..config import LASERS_PER_FRAME
        with self._blob(obj).open("rb") as f: return pq.ParquetFile(f).metadata.num_rows // LASERS_PER_FRAME
