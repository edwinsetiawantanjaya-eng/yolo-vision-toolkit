"""Step 2: split data/raw into train/val/test and write dataset.yaml. Usage: python prepare_dataset.py"""
import core

if __name__ == "__main__":
    core.prepare_dataset(core.load_config())
