"""
core/management/commands/train_categorizer.py
Django management command to train or retrain the hybrid expense categorizer.
Generates a realistic student UPI transaction training set, fits the calibrated
RandomForest model, and overwrites the artifact under backend/ml_models/.
"""

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from core.services.categorization_service import (
    train_model,
    generate_synthetic_dataset,
    MODEL_PATH,
    CATEGORIES,
)


class Command(BaseCommand):
    help = "Train the hybrid expense categorizer model and save artifact under backend/ml_models/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default=MODEL_PATH,
            help="Custom target filepath for the saved .joblib model",
        )
        parser.add_argument(
            "--info",
            action="store_true",
            help="Display category breakdown and information",
        )

    def handle(self, *args, **options):
        output_path = options.get("output") or MODEL_PATH
        self.stdout.write(self.style.NOTICE("Generating realistic student UPI dataset..."))

        df = generate_synthetic_dataset()
        self.stdout.write(
            f"Dataset generated with {len(df)} samples across {df['category'].nunique()} categories."
        )

        if options.get("info"):
            for cat, count in df["category"].value_counts().items():
                self.stdout.write(f"  - {cat}: {count} samples")

        self.stdout.write(self.style.NOTICE("Training CalibratedClassifierCV(RandomForestClassifier)..."))
        pipeline, metrics = train_model(df=df, save_path=output_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully trained and saved model artifact to: {metrics['saved_to']}\n"
                f"Classes ({metrics['categories_count']}): {', '.join(sorted(metrics['categories']))}"
            )
        )
