import logging

import apache_beam as beam
from apache_beam.io.filesystems import FileSystems
from google.cloud import storage
from google.cloud.storage.retry import DEFAULT_RETRY


class ReadPage(beam.DoFn):
    def __init__(self, project):
        self.project = project
        self.client = None

    def setup(self):
        self.client = storage.Client(project=self.project)
        self.retry = DEFAULT_RETRY.with_timeout(300)
        self.completed = 0

    def process(self, metadata):
        path = metadata.path

        if path.startswith("gs://"):
            bucket_name, object_name = path[5:].split("/", 1)
            blob = self.client.bucket(bucket_name).blob(object_name)
            content = blob.download_as_bytes(
                timeout=(20, 60),
                retry=self.retry,
            )
        else:
            with FileSystems.open(path) as stream:
                content = stream.read()

        self.completed += 1
        if self.completed % 100 == 0:
            logging.info(
                "Reader instance completed %s files; latest: %s",
                self.completed,
                path,
            )

        yield path.rsplit("/", 1)[-1], content.decode("utf-8")

    def teardown(self):
        if self.client is not None:
            self.client.close()
