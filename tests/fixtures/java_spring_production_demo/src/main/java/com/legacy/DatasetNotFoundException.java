package com.legacy;

public class DatasetNotFoundException extends RuntimeException {
    public DatasetNotFoundException(String datasetId) {
        super("Dataset not found: " + datasetId);
    }
}
