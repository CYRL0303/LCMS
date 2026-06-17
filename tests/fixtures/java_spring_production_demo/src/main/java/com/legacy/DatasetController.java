package com.legacy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DatasetController {
    private final DatasetService datasetService;

    public DatasetController(DatasetService datasetService) {
        this.datasetService = datasetService;
    }

    @GetMapping("/api/dataset/version")
    public String getVersion(@RequestParam("datasetId") String datasetId) {
        return datasetService.getVersion(datasetId);
    }
}
