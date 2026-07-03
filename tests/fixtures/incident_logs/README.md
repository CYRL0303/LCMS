# Incident Log Fixtures

Reusable incident samples for Structure2 alert intake tests.

The `ibm/` fixtures target the Java/Spring Boot/MyBatis style used by
`Lsdaer-1/Intelligent-Book-Management-System`. They are intentionally plain
production-like log and webhook payload samples, not mocked parser responses.

Expected signal extraction with the current `parse_alert_event` rules:

| Fixture | error_type | suspected_location | query_terms |
| --- | --- | --- | --- |
| `ibm/spring-startup-bean-missing.log` | `UnsatisfiedDependencyException` | `BookController.setBookService` | `UnsatisfiedDependencyException`, `BookController.setBookService`, `/api/books/list` |
| `ibm/book-query-sql-error.log` | `BadSqlGrammarException` | `BookMapper.selectAvailableBooks` | `BadSqlGrammarException`, `BookMapper.selectAvailableBooks`, `/api/books/search`, `book` |
| `ibm/login-null-pointer.log` | `NullPointerException` | `LoginController.login` | `NullPointerException`, `LoginController.login`, `/api/login` |
| `ibm/generic-alert.json` | `DataIntegrityViolationException` | `BookService.borrowBook` | `DataIntegrityViolationException`, `BookService.borrowBook`, `/api/books/borrow`, `borrow_record` |
