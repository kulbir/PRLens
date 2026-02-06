"""Parser for unified diff format using unidiff library."""

from dataclasses import dataclass, field
from unidiff import PatchSet


@dataclass
class DiffLineMapping:
    """Maps actual line numbers to diff positions for a file."""
    filename: str
    # Maps line number (in new file) -> position in diff (1-based)
    line_to_position: dict[int, int] = field(default_factory=dict)
    # Set of valid line numbers that can receive comments
    valid_lines: set[int] = field(default_factory=set)


@dataclass
class FileDiff:
    """Parsed diff for a single file."""
    filename: str
    status: str                           # added, deleted, modified, renamed
    additions: int                        # count of added lines
    deletions: int                        # count of deleted lines
    added_lines: list[tuple[int, str]] = field(default_factory=list)   # (line_num, content)
    deleted_lines: list[tuple[int, str]] = field(default_factory=list) # (line_num, content)
    patch: str = ""                       # raw patch text


def parse_diff(diff_text: str) -> list[FileDiff]:
    """
    Parse a unified diff into structured FileDiff objects.
    
    Args:
        diff_text: Raw unified diff string
        
    Returns:
        List of FileDiff objects, one per file
    """
    patch_set = PatchSet(diff_text)
    files = []
    
    for patched_file in patch_set:
        # Determine status
        if patched_file.is_added_file:
            status = "added"
        elif patched_file.is_removed_file:
            status = "deleted"
        elif patched_file.is_rename:
            status = "renamed"
        else:
            status = "modified"
        
        # Extract added and deleted lines with line numbers
        added_lines = []
        deleted_lines = []
        
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_lines.append((line.target_line_no, line.value.rstrip('\n')))
                elif line.is_removed:
                    deleted_lines.append((line.source_line_no, line.value.rstrip('\n')))
        
        files.append(FileDiff(
            filename=patched_file.path,
            status=status,
            additions=patched_file.added,
            deletions=patched_file.removed,
            added_lines=added_lines,
            deleted_lines=deleted_lines,
            patch=str(patched_file),
        ))
    
    return files


def build_line_mapping(diff_text: str) -> dict[str, DiffLineMapping]:
    """
    Build a mapping from line numbers to diff positions for all files.
    
    GitHub's review API needs either:
    - position: 1-based offset within the diff hunk (legacy)
    - line + side: actual line number with LEFT/RIGHT (modern)
    
    We use the modern API (line + side), but this function also builds
    the position mapping for fallback and helps validate which lines
    are actually in the diff (you can only comment on changed lines).
    
    Args:
        diff_text: Raw unified diff string
        
    Returns:
        Dict mapping filename -> DiffLineMapping
    """
    patch_set = PatchSet(diff_text)
    mappings = {}
    
    for patched_file in patch_set:
        filename = patched_file.path
        mapping = DiffLineMapping(filename=filename)
        
        position = 0  # Position counter across all hunks
        
        for hunk in patched_file:
            for line in hunk:
                position += 1
                
                # We can only comment on lines that appear in the diff
                # For added/modified lines, use target_line_no (new file)
                # For removed lines, use source_line_no (old file)
                
                if line.is_added or line.is_context:
                    # These lines exist in the new version of the file
                    if line.target_line_no is not None:
                        mapping.line_to_position[line.target_line_no] = position
                        mapping.valid_lines.add(line.target_line_no)
        
        mappings[filename] = mapping
    
    return mappings


def find_nearest_valid_line(
    mapping: DiffLineMapping, 
    target_line: int,
    max_distance: int = 5
) -> int | None:
    """
    Find the nearest valid line in the diff to the target line.
    
    Sometimes AI findings reference lines that aren't in the diff
    (e.g., context around the change). This finds the closest line
    that we can actually comment on.
    
    Args:
        mapping: DiffLineMapping for the file
        target_line: The line number we want to comment on
        max_distance: Maximum lines away to search
        
    Returns:
        Nearest valid line number, or None if none within range
    """
    if target_line in mapping.valid_lines:
        return target_line
    
    # Search outward from target
    for distance in range(1, max_distance + 1):
        if target_line + distance in mapping.valid_lines:
            return target_line + distance
        if target_line - distance in mapping.valid_lines:
            return target_line - distance
    
    return None


def validate_finding_lines(
    findings: list[dict],
    mappings: dict[str, DiffLineMapping],
    max_distance: int = 5
) -> tuple[list[dict], list[dict]]:
    """
    Validate and adjust findings to ensure they map to valid diff lines.
    
    Args:
        findings: List of findings with 'path' and 'line' keys
        mappings: Dict of filename -> DiffLineMapping
        max_distance: How far to search for nearest valid line
        
    Returns:
        Tuple of (valid_findings, unmapped_findings)
        - valid_findings: Findings with adjusted line numbers
        - unmapped_findings: Findings that couldn't be mapped
    """
    valid = []
    unmapped = []
    
    for finding in findings:
        path = finding.get("path", "")
        line = finding.get("line")
        
        # If no line specified, can't post as inline comment
        if line is None:
            unmapped.append(finding)
            continue
        
        # If file not in diff, can't comment
        if path not in mappings:
            unmapped.append(finding)
            continue
        
        mapping = mappings[path]
        valid_line = find_nearest_valid_line(mapping, line, max_distance)
        
        if valid_line is not None:
            adjusted_finding = finding.copy()
            adjusted_finding["line"] = valid_line
            if valid_line != line:
                adjusted_finding["original_line"] = line
            valid.append(adjusted_finding)
        else:
            unmapped.append(finding)
    
    return valid, unmapped


# File extensions to skip during review
SKIP_EXTENSIONS = {
    '.md', '.txt', '.rst', '.adoc',           # Docs
    '.lock',                                   # Lock files
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',  # Images
    '.woff', '.woff2', '.ttf', '.eot',        # Fonts
    '.csv', '.json', '.xml', '.yaml', '.yml', '.toml',  # Data
    '.min.js', '.min.css', '.map',            # Build artifacts
    '.exe', '.dll', '.so', '.dylib', '.pyc',  # Binary
    '.zip', '.tar', '.gz', '.pdf',            # Archives/docs
}

SKIP_FILENAMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'Pipfile.lock', 'poetry.lock', 'composer.lock',
    'Gemfile.lock', 'Cargo.lock', 'uv.lock',
    '.gitignore', '.gitattributes', '.editorconfig',
    'LICENSE', 'LICENSE.md', 'LICENSE.txt',
}

SKIP_DIRECTORIES = {'node_modules/', 'vendor/', 'dist/', 'build/', '.git/', '__pycache__/', '.venv/'}


def should_review_file(filename: str) -> bool:
    """Check if file should be reviewed based on name/extension."""
    # Check directory
    for skip_dir in SKIP_DIRECTORIES:
        if filename.startswith(skip_dir) or f'/{skip_dir}' in filename:
            return False
    
    # Check exact filename
    basename = filename.split('/')[-1]
    if basename in SKIP_FILENAMES:
        return False
    
    # Check extension
    for ext in SKIP_EXTENSIONS:
        if filename.lower().endswith(ext):
            return False
    
    return True


def filter_files(files: list[FileDiff], include_deletions: bool = False) -> list[FileDiff]:
    """Filter out files that shouldn't be reviewed."""
    result = []
    
    for file in files:
        if not should_review_file(file.filename):
            continue
        if not include_deletions and file.status == 'deleted':
            continue
        if not include_deletions and len(file.added_lines) == 0:
            continue
        result.append(file)
    
    return result


def extract_added_code(file: FileDiff, include_line_numbers: bool = True) -> str:
    """
    Extract only the added lines as a code string.
    
    Args:
        file: FileDiff object
        include_line_numbers: If True, prefix each line with its line number
        
    Returns:
        String containing only the new code, ready for review
    """
    if not file.added_lines:
        return ""
    
    lines = []
    for line_num, content in file.added_lines:
        if include_line_numbers:
            lines.append(f"{line_num:4}| {content}")
        else:
            lines.append(content)
    
    return "\n".join(lines)


def get_review_content(file: FileDiff) -> dict:
    """
    Get file content formatted for LLM review.
    
    Returns:
        Dict with filename, status, and code to review
    """
    return {
        "filename": file.filename,
        "status": file.status,
        "total_additions": file.additions,
        "code": extract_added_code(file, include_line_numbers=True),
    }


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    from github_client import fetch_raw_diff
    
    TEST_REPO = "kulbir/PRLens"
    TEST_PR = 1
    
    print("Fetching diff...")
    raw_diff = fetch_raw_diff(TEST_REPO, TEST_PR)
    
    print("\nParsing diff with unidiff...")
    all_files = parse_diff(raw_diff)
    filtered = filter_files(all_files)
    
    print(f"\nFiles to review: {len(filtered)}")
    
    for f in filtered:
        print(f"\n{'='*60}")
        print(f"📄 {f.filename} ({f.status}, +{f.additions} lines)")
        print('='*60)
        
        # Extract just the added code
        added_code = extract_added_code(f)
        
        # Show preview (first 20 lines)
        lines = added_code.split('\n')
        preview = '\n'.join(lines[:20])
        print(preview)
        
        if len(lines) > 20:
            print(f"\n... and {len(lines) - 20} more lines")
        
        # Show what would be sent to LLM
        print(f"\n{'='*60}")
        print("REVIEW CONTENT (for Gemini):")
        print('='*60)
        review = get_review_content(f)
        print(f"Filename: {review['filename']}")
        print(f"Status: {review['status']}")
        print(f"Lines to review: {review['total_additions']}")
