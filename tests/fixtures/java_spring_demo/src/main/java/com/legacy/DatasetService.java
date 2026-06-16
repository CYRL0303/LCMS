package com.legacy;

import org.springframework.stereotype.Service;

@Service
public class DatasetService {
    private final DatasetMapper datasetMapper;

    public DatasetService(DatasetMapper datasetMapper) {
        this.datasetMapper = datasetMapper;
    }

    public String getVersion(String datasetId) {
        if (datasetId == null || datasetId.isBlank()) {
            return "unknown";
        }
        return datasetMapper.selectVersionById(datasetId);
    }
}
