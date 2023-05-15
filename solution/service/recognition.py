from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
import threading

from infrastructure.models import BaseTextClassificationModel, TextClassificationModelData


class TextClassificationService:

    def __init__(self, models: List[BaseTextClassificationModel]):
        self.service_models = models

    def get_results(self, input_text: str) -> List[TextClassificationModelData]:
        results = []
        threads = []
        for model in self.service_models:
            t = threading.Thread(target=lambda: results.append(model(input_text)))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        return results

