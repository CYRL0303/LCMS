package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;

/**
 * Extension point for language/framework-specific parsers.
 */
public interface CodeParser {
    boolean supports(ProjectAnalysisContext context);

    CodeParseResult parse(ProjectAnalysisContext context);
}
