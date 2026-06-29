package com.legacypilot.repository.entity;

/**
 * Source mode used when connecting a repository.
 */
public enum RepositorySourceType {
    /** User provides an existing local Git working tree path. */
    LOCAL_PATH,
    /** User provides a remote Git URL; clone support is planned later. */
    GIT_URL
}
