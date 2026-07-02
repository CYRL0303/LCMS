package com.legacypilot.agenttool.query.service;

import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Rule-based query understanding tool.
 *
 * This is a placeholder for the future Qwen-backed implementation. It keeps the
 * tool contract stable while intent detection and search planning evolve.
 */
@Service
public class QueryUnderstandingService {
    private static final Logger log = LoggerFactory.getLogger(QueryUnderstandingService.class);

    private static final Set<String> ENGLISH_STOP_WORDS = Set.of(
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "to", "of", "for", "from", "in", "on", "at", "by", "with",
            "and", "or", "but", "this", "that", "these", "those",
            "please", "help", "check", "look", "into", "why", "what",
            "where", "when", "how", "issue", "problem", "error", "fail",
            "failed", "failure", "endpoint", "api", "service", "project",
            "code", "show", "find", "get", "list", "tell", "me"
    );

    private static final Set<String> CHINESE_STOP_PHRASES = Set.of(
            "接口", "问题", "报错", "失败", "帮我", "看看", "可能", "哪里",
            "为什么", "一个", "这个", "那个", "出现", "有问题", "分析",
            "一下", "怎么", "什么", "是否", "能不能", "我想", "需要"
    );

    private static final Set<String> ERROR_SIGNAL_WORDS = Set.of(
            "400", "401", "403", "404", "409", "422", "429", "500", "502", "503",
            "timeout", "timedout", "nullpointer", "npe", "exception", "badrequest",
            "notfound", "unauthorized", "forbidden", "crash", "超时", "异常", "空指针",
            "连接失败", "参数错误", "权限错误", "内部错误", "服务不可用"
    );

    private static final Set<String> RCA_TERMS = Set.of(
            "报错", "失败", "异常", "空指针", "超时", "崩溃", "无法访问", "连接失败",
            "500", "502", "503", "400", "404", "error", "exception", "failed",
            "failure", "timeout", "crash", "npe", "nullpointer"
    );

    private static final Set<String> ENDPOINT_TERMS = Set.of(
            "接口", "路由", "控制器", "endpoint", "api", "route", "controller",
            "requestmapping", "getmapping", "postmapping", "putmapping", "deletemapping"
    );

    private static final Set<String> GRAPH_TERMS = Set.of(
            "图谱", "调用链", "依赖", "关系", "模块关系", "结构图", "graph",
            "call", "chain", "dependency", "dependencies", "relation", "relationship"
    );

    private static final Set<String> CODE_LOOKUP_TERMS = Set.of(
            "类", "方法", "文件", "位置", "在哪里", "源码", "代码位置", "class",
            "method", "function", "file", "source", "symbol"
    );

    private static final Set<String> SUMMARY_TERMS = Set.of(
            "总结", "概览", "整体", "项目结构", "干什么", "介绍", "summary",
            "summarize", "overview", "describe"
    );

    private static final Set<String> TECHNICAL_KEYWORDS = Set.of(
            "endpoint", "api", "route", "controller", "service", "repository",
            "graph", "node", "edge", "method", "class", "file", "spring",
            "bean", "mapper", "database", "sql", "http", "request", "response",
            "接口", "路由", "控制器", "服务", "仓储", "图谱", "节点", "边",
            "方法", "类", "文件", "调用链", "数据库", "参数", "权限", "登录",
            "注册", "订单", "取消", "支付", "用户", "项目", "源码"
    );

    public QueryUnderstandingResult understand(String question) {
        String rawQuestion = question == null ? "" : question.trim();
        String normalizedQuestion = normalizeQuestion(rawQuestion);
        List<String> errorSignals = extractErrorSignals(normalizedQuestion);
        String intent = detectIntent(normalizedQuestion, errorSignals);
        String targetType = detectTargetType(normalizedQuestion, intent);
        List<String> keywords = extractKeywords(rawQuestion, normalizedQuestion, errorSignals);
        List<String> searchPlan = buildSearchPlan(intent, targetType);

        log.info("QueryUnderstandingTool识别完成：intent={}，targetType={}，keywords={}，errorSignals={}，searchPlan={}",
                intent,
                targetType,
                keywords,
                errorSignals,
                searchPlan
        );

        return new QueryUnderstandingResult(
                rawQuestion,
                intent,
                targetType,
                keywords,
                errorSignals,
                searchPlan
        );
    }

    private String detectIntent(String normalizedQuestion, List<String> errorSignals) {
        if (!errorSignals.isEmpty() || containsAny(normalizedQuestion, RCA_TERMS)) {
            return "RCA";
        }
        if (containsAny(normalizedQuestion, SUMMARY_TERMS)) {
            return "SUMMARIZE_PROJECT";
        }
        if (containsAny(normalizedQuestion, GRAPH_TERMS)) {
            return "EXPLORE_GRAPH";
        }
        if (containsAny(normalizedQuestion, ENDPOINT_TERMS)) {
            return "EXPLORE_ENDPOINT";
        }
        if (containsAny(normalizedQuestion, CODE_LOOKUP_TERMS)) {
            return "LOOKUP_CODE";
        }
        return "UNKNOWN";
    }

    private String detectTargetType(String normalizedQuestion, String intent) {
        if (containsAny(normalizedQuestion, ENDPOINT_TERMS)) {
            return "ENDPOINT";
        }
        if (containsAny(normalizedQuestion, GRAPH_TERMS)) {
            return "GRAPH";
        }
        if (containsAny(normalizedQuestion, Set.of("类", "class"))) {
            return "CLASS";
        }
        if (containsAny(normalizedQuestion, Set.of("方法", "method", "function"))) {
            return "METHOD";
        }
        if (containsAny(normalizedQuestion, Set.of("文件", "file", "source", "源码"))) {
            return "FILE";
        }
        return switch (intent) {
            case "RCA", "EXPLORE_ENDPOINT" -> "ENDPOINT";
            case "EXPLORE_GRAPH", "SUMMARIZE_PROJECT" -> "GRAPH";
            case "LOOKUP_CODE" -> "SYMBOL";
            default -> "UNKNOWN";
        };
    }

    private List<String> buildSearchPlan(String intent, String targetType) {
        if ("RCA".equals(intent) && "ENDPOINT".equals(targetType)) {
            return List.of("FIND_ENDPOINT", "FETCH_ENDPOINT_EVIDENCE", "TRACE_METHOD_CALLS");
        }
        if ("EXPLORE_ENDPOINT".equals(intent)) {
            return List.of("LIST_ENDPOINTS", "RANK_ENDPOINTS", "FETCH_ENDPOINT_EVIDENCE");
        }
        if ("EXPLORE_GRAPH".equals(intent)) {
            return List.of("LOAD_CODE_GRAPH", "SUMMARIZE_GRAPH");
        }
        if ("LOOKUP_CODE".equals(intent)) {
            return List.of("SEARCH_CODE_SYMBOL", "FETCH_SOURCE_EVIDENCE");
        }
        if ("SUMMARIZE_PROJECT".equals(intent)) {
            return List.of("LOAD_CODE_GRAPH", "LIST_ENDPOINTS", "SUMMARIZE_PROJECT");
        }
        return List.of("ASK_CLARIFYING_QUESTION");
    }

    private List<String> extractKeywords(
            String rawQuestion,
            String normalizedQuestion,
            List<String> errorSignals
    ) {
        Set<String> keywords = new LinkedHashSet<>();

        for (String token : normalizedQuestion.split("[^\\p{IsAlphabetic}\\p{IsDigit}\\p{IsHan}]+")) {
            if (token.isBlank()) {
                continue;
            }
            if (containsHan(token)) {
                addChineseKeywords(keywords, token);
            } else {
                addEnglishKeyword(keywords, token);
            }
        }

        addKnownTerms(keywords, normalizedQuestion, TECHNICAL_KEYWORDS);
        keywords.addAll(errorSignals);
        removeStopWords(keywords);

        if (keywords.isEmpty() && rawQuestion != null && !rawQuestion.isBlank()) {
            keywords.add(rawQuestion.trim());
        }
        return new ArrayList<>(keywords);
    }

    private List<String> extractErrorSignals(String normalizedQuestion) {
        Set<String> errorSignals = new LinkedHashSet<>();
        for (String signal : ERROR_SIGNAL_WORDS) {
            if (normalizedQuestion.contains(signal.toLowerCase(Locale.ROOT))) {
                errorSignals.add(signal);
            }
        }
        return new ArrayList<>(errorSignals);
    }

    private void addEnglishKeyword(Set<String> keywords, String token) {
        if (token.length() < 2 || ENGLISH_STOP_WORDS.contains(token)) {
            return;
        }
        keywords.add(token);
        for (String part : token.split("(?<=\\D)(?=\\d)|(?<=\\d)(?=\\D)")) {
            if (part.length() >= 2 && !ENGLISH_STOP_WORDS.contains(part)) {
                keywords.add(part);
            }
        }
    }

    private void addChineseKeywords(Set<String> keywords, String token) {
        String text = keepHanOnly(token);
        if (text.length() < 2) {
            return;
        }

        String reduced = text;
        for (String stopPhrase : CHINESE_STOP_PHRASES) {
            reduced = reduced.replace(stopPhrase, " ");
        }

        for (String phrase : reduced.split("\\s+")) {
            if (phrase.length() >= 2 && phrase.length() <= 12 && !CHINESE_STOP_PHRASES.contains(phrase)) {
                keywords.add(phrase);
            }
        }
    }

    private void addKnownTerms(Set<String> keywords, String normalizedQuestion, Set<String> terms) {
        for (String term : terms) {
            if (normalizedQuestion.contains(term.toLowerCase(Locale.ROOT))) {
                keywords.add(term);
            }
        }
    }

    private void removeStopWords(Set<String> keywords) {
        keywords.removeIf(keyword ->
                keyword == null
                        || keyword.isBlank()
                        || ENGLISH_STOP_WORDS.contains(keyword)
                        || CHINESE_STOP_PHRASES.contains(keyword)
        );
    }

    private boolean containsAny(String normalizedQuestion, Set<String> terms) {
        for (String term : terms) {
            if (normalizedQuestion.contains(term.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private String normalizeQuestion(String question) {
        return splitCamelCase(question == null ? "" : question)
                .replace('-', ' ')
                .replace('_', ' ')
                .toLowerCase(Locale.ROOT);
    }

    private String splitCamelCase(String value) {
        return value.replaceAll("(?<=[a-z0-9])(?=[A-Z])", " ");
    }

    private String keepHanOnly(String value) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (isHan(ch)) {
                builder.append(ch);
            }
        }
        return builder.toString();
    }

    private boolean containsHan(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (isHan(value.charAt(i))) {
                return true;
            }
        }
        return false;
    }

    private boolean isHan(char ch) {
        Character.UnicodeScript script = Character.UnicodeScript.of(ch);
        return script == Character.UnicodeScript.HAN;
    }
}
