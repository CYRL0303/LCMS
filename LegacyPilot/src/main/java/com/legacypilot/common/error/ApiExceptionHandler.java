package com.legacypilot.common.error;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/**
 * Converts expected service-layer failures into readable API responses.
 */
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ApiErrorResponse> handleResponseStatusException(
            ResponseStatusException exception,
            HttpServletRequest request
    ) {
        int status = exception.getStatusCode().value();
        return ResponseEntity
                .status(exception.getStatusCode())
                .body(new ApiErrorResponse(
                        status,
                        exception.getStatusCode().toString(),
                        exception.getReason(),
                        request.getRequestURI()
                ));
    }
}
