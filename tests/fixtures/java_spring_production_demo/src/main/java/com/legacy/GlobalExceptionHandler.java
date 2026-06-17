package com.legacy;

import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(DatasetNotFoundException.class)
    public String handleDatasetNotFound(DatasetNotFoundException exception) {
        return exception.getMessage();
    }
}
