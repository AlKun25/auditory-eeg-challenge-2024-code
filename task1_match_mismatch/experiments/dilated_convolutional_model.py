"""Example experiment for dilation model."""
import glob
import json
import logging
import os
import tensorflow as tf

from task1_match_mismatch.models.dilated_convolutional_model import dilation_model
from task1_match_mismatch.util.dataset_generator import (
    MatchMismatchDataGenerator,
    default_batch_equalizer_fn,
)
from util.dataset_generator import create_tf_dataset
from util.config import load_config
from util.log import enable_logging


def evaluate_model(model, test_dict):
    """Evaluate a model.

    Parameters
    ----------
    model: tf.keras.Model
        Model to evaluate.
    test_dict: dict
        Mapping between a subject and a tf.data.Dataset containing the test
        set for the subject.

    Returns
    -------
    dict
        Mapping between a subject and the loss/evaluation score on the test set
    """
    evaluation = {}
    for subject, ds_test in test_dict.items():
        logging.info(f"Scores for subject {subject}:")
        results = model.evaluate(ds_test, verbose=2)
        metrics = model.metrics_names
        evaluation[subject] = dict(zip(metrics, results))
    return evaluation


if __name__ == "__main__":
    enable_logging()

    # Parameters
    # Length of the decision window
    window_length = 5 * 64  # 3 seconds
    # Hop length between two consecutive decision windows
    hop_length = 64
    # Number of samples (space) between end of matched speech and beginning of mismatched speech
    spacing = 64
    epochs = 100
    patience = 5
    batch_size = 64
    only_evaluate = False
    training_log_filename = "training_log.csv"
    results_filename = 'eval.json'

    # Provide the path of the dataset
    # which is split already to train, val, test
    experiments_folder = os.path.dirname(os.path.abspath(__file__))
    root_folder = os.path.dirname(os.path.dirname(experiments_folder))
    config = load_config(os.path.join(root_folder, "config.json"))
    data_folder = os.path.join(config["dataset_folder"], config["split_folder"])
    stimulus_features = ["envelope"]
    features = ["eeg"] + stimulus_features

    # Create a directory to store (intermediate) results
    results_folder = os.path.join(
        experiments_folder, "results_dilated_convolutional_model"
    )
    os.makedirs(results_folder, exist_ok=True)

    # create dilation model
    model = dilation_model(time_window=window_length)
    model_path = os.path.join(results_folder, "model.h5")

    if only_evaluate:
        model = tf.keras.models.load_model(model_path)
    else:

        train_files = [
            x
            for x in glob.glob(os.path.join(data_folder, "train_-_*"))
            if os.path.basename(x).split("_-_")[-1].split(".")[0] in features
        ]
        # Create list of numpy array files
        dataset_train = create_tf_dataset(
            MatchMismatchDataGenerator(train_files, window_length, spacing=spacing),
            window_length,
            default_batch_equalizer_fn,
            hop_length,
            batch_size,
        )

        # Create the generator for the validation set
        val_files = [
            x
            for x in glob.glob(os.path.join(data_folder, "val_-_*"))
            if os.path.basename(x).split("_-_")[-1].split(".")[0] in features
        ]
        dataset_val = create_tf_dataset(
            MatchMismatchDataGenerator(val_files, window_length, spacing=spacing),
            window_length,
            default_batch_equalizer_fn,
            hop_length,
            batch_size,
        )

        # Train the model
        model.fit(
            dataset_train,
            epochs=epochs,
            validation_data=dataset_val,
            callbacks=[
                tf.keras.callbacks.ModelCheckpoint(model_path, save_best_only=True),
                tf.keras.callbacks.CSVLogger(
                    os.path.join(results_folder, training_log_filename)
                ),
                tf.keras.callbacks.EarlyStopping(patience=patience, restore_best_weights=True),
            ],
        )

    # Evaluate the model on test set
    # Create a dataset generator for each test subject
    test_files = [
        x
        for x in glob.glob(os.path.join(data_folder, "test_-_*"))
        if os.path.basename(x).split("_-_")[-1].split(".")[0] in features
    ]
    # Get all different subjects from the test set
    subjects = list(set([os.path.basename(x).split("_-_")[1] for x in test_files]))
    datasets_test = {}
    # Create a generator for each subject
    for sub in subjects:
        files_test_sub = [f for f in test_files if sub in os.path.basename(f)]
        datasets_test[sub] = create_tf_dataset(
            MatchMismatchDataGenerator(files_test_sub, window_length, spacing=spacing),
            window_length,
            default_batch_equalizer_fn,
            hop_length,
            1,
        )

    # Evaluate the model
    evaluation = evaluate_model(model, datasets_test)

    # We can save our results in a json encoded file
    results_path = os.path.join(results_folder, results_filename)
    with open(results_path, "w") as fp:
        json.dump(evaluation, fp)
    logging.info(f"Results saved at {results_path}")