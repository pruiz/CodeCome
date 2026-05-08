# PHP Security Skill

Use this skill when the target contains PHP source code, PHP web applications, PHP libraries, Composer packages, legacy PHP applications, CMS plugins, framework-based PHP projects, or mixed repositories with PHP components.

This skill supports reconnaissance, vulnerability hypothesis generation, counter-analysis, validation, and reporting for PHP targets.

## Scope

Relevant files include:

- `.php`
- `.phtml`
- `.inc`
- `.module`
- `.theme`
- `composer.json`
- `composer.lock`
- `index.php`
- `.htaccess`
- `php.ini`
- `Dockerfile`
- `docker-compose.yml`
- framework config files
- template files
- route definitions
- controllers
- middleware
- service classes
- model/repository classes
- migration files
- CMS plugin/module files

Relevant PHP ecosystems include:

- plain PHP,
- legacy PHP applications,
- Laravel,
- Symfony,
- Slim,
- Laminas/Zend,
- CodeIgniter,
- CakePHP,
- Yii,
- WordPress,
- Drupal,
- Magento,
- PrestaShop,
- custom CMS code,
- Composer packages.

## Reconnaissance focus

During reconnaissance, identify:

- framework or CMS,
- PHP version assumptions,
- Composer dependencies,
- public web root,
- entrypoints,
- routing model,
- controllers,
- middleware,
- authentication model,
- authorization model,
- session handling,
- CSRF protections,
- request input handling,
- database access layer,
- ORM/query builder usage,
- template engine,
- file upload/download paths,
- filesystem access,
- deserialization usage,
- XML parsing,
- external HTTP calls,
- command execution,
- cryptographic operations,
- secrets and configuration,
- deployment assumptions.

## Common entrypoints

Look for:

- `public/index.php`
- `index.php`
- `router.php`
- front controllers,
- route files,
- controller classes,
- API endpoint files,
- WordPress hooks/actions/shortcodes,
- Drupal routes/controllers/forms,
- CLI commands,
- cron scripts,
- queue workers,
- webhook handlers,
- upload handlers,
- download handlers,
- admin pages.

## PHP version-specific considerations

Pin findings to the PHP version detected during reconnaissance. Several
vulnerability classes are version-dependent:

- **Null byte truncation** in filesystem functions (`fopen`, `include`,
  `file_get_contents`) — fixed in PHP 5.3.4. Still relevant for legacy targets.
- **`preg_replace` `/e` modifier** — code-execution sink. Removed in PHP 7.0.
  Only relevant for PHP 5.x targets or legacy code paths.
- **`create_function`** — deprecated in PHP 7.2, removed in PHP 8.0.
  Effectively `eval()`; still common in older codebases.
- **`assert(string)`** — string argument is `eval`'d in PHP 5.x and 7.0;
  deprecated in 7.2; removed in PHP 8.0.
- **Phar stream wrapper deserialization** — restricted by
  `Phar::interceptFileFuncs` behavior changes in PHP 8.0+, but many
  filesystem functions still trigger it.
- **String-to-number loose comparison** changed in PHP 8.0:
  `0 == "abc"` is now `false` (was `true` in 7.x). Type juggling auth
  bypasses tied to numeric strings may not reproduce on PHP 8+.
- **`strcmp` / `strpos` with array argument** — emits warning and returns
  `null` in PHP 7.x; throws `TypeError` in PHP 8.0+. Auth bypasses based on
  this behavior may be PHP 7.x-only.
- **`unserialize` `allowed_classes` option** — available since PHP 7.0.
  Pre-7.0 codebases cannot use this defense.

## High-risk vulnerability classes

Prioritize:

- SQL injection,
- command injection,
- PHP object injection / unsafe deserialization,
- Phar deserialization via filesystem functions,
- type juggling / loose comparison bypass,
- local file inclusion,
- remote file inclusion,
- path traversal,
- arbitrary file upload,
- unsafe file download,
- authentication bypass,
- authorization bypass,
- IDOR / broken object-level authorization,
- CSRF,
- XSS,
- SSRF,
- open redirect,
- template injection,
- XML external entity injection,
- mass assignment,
- insecure direct use of request parameters,
- insecure session handling,
- weak password reset flows,
- secrets exposure,
- insecure cryptography,
- insecure randomness,
- unsafe dynamic code execution,
- insecure dependency or autoload behavior.

## Dangerous PHP functions and constructs

Review uses of:

    eval
    assert
    create_function
    include
    include_once
    require
    require_once
    system
    exec
    shell_exec
    passthru
    proc_open
    popen
    backticks
    unserialize
    call_user_func
    call_user_func_array
    preg_replace with /e modifier
    extract
    parse_str
    file_get_contents
    file_put_contents
    fopen
    fread
    fwrite
    unlink
    rename
    copy
    move_uploaded_file
    glob
    scandir
    opendir
    readfile
    header
    mail
    curl_exec
    simplexml_load_string
    simplexml_load_file
    DOMDocument::loadXML
    DOMDocument::load
    new ReflectionClass
    new $className
    $$variable
    variable functions

Do not report a finding just because one of these appears.

A finding requires attacker control, reachability, impact, and a validation plan.

## Input sources

Track data from:

    $_GET
    $_POST
    $_REQUEST
    $_COOKIE
    $_FILES
    $_SERVER
    php://input
    HTTP headers
    route parameters
    JSON request bodies
    XML request bodies
    uploaded files
    session data influenced by users
    database fields previously controlled by users
    webhook payloads
    CLI arguments
    environment variables
    config files
    queue messages
    cache entries

Be careful with second-order vulnerabilities where data was stored earlier and used later in a dangerous context.

## SQL injection review

Look for user-controlled input reaching:

- raw SQL strings,
- concatenated SQL,
- dynamic `WHERE` clauses,
- dynamic `ORDER BY`,
- dynamic table names,
- dynamic column names,
- stored procedure calls,
- query builder raw expressions,
- ORM raw queries.

Dangerous patterns include:

    mysqli_query($conn, "SELECT ... " . $_GET["id"])
    $pdo->query("SELECT ... $id")
    $db->raw("ORDER BY " . $_GET["sort"])
    DB::raw($request->input("field"))
    whereRaw($userInput)
    orderByRaw($userInput)

Safer patterns include:

- prepared statements,
- bound parameters,
- ORM parameter binding,
- allowlisted dynamic columns or sort directions.

Do not report SQL injection only because SQL is used. Show the unsafe construction and the attacker-controlled path.

## Command injection review

Look for user-controlled input reaching:

    system
    exec
    shell_exec
    passthru
    proc_open
    popen
    backticks

Check:

- shell metacharacters,
- quoting,
- escaping,
- argument separation,
- environment variables,
- working directory,
- PATH usage,
- privilege context.

Escaping with `escapeshellarg()` or `escapeshellcmd()` may help, but verify usage and platform assumptions.

Prefer findings where the exact command construction path is shown.

## File inclusion review

Look for user-controlled input reaching:

    include
    include_once
    require
    require_once

Risks:

- local file inclusion,
- remote file inclusion when enabled,
- path traversal,
- log poisoning,
- session file inclusion,
- wrapper abuse such as `php://filter`,
- Phar deserialization side effects.

Check PHP configuration assumptions:

- `allow_url_include`,
- `allow_url_fopen`,
- upload directories,
- include path.

## Path traversal and filesystem review

Look for user-controlled input reaching:

- file reads,
- file writes,
- delete operations,
- copy/move operations,
- downloads,
- archive extraction,
- template loading,
- cache file paths,
- log file paths.

Dangerous APIs include:

    file_get_contents
    file_put_contents
    fopen
    readfile
    unlink
    rename
    copy
    move_uploaded_file
    ZipArchive::extractTo

Check:

- canonicalization,
- `realpath`,
- base directory enforcement,
- prefix checks before/after normalization,
- symlinks,
- extension allowlists,
- original upload filenames,
- path separators,
- null byte assumptions in legacy PHP.

## File upload review

Check:

- allowed extensions,
- MIME/content checks,
- server-side renaming,
- storage outside web root,
- executable extensions,
- double extensions,
- case sensitivity,
- `.htaccess` behavior,
- image processing,
- archive extraction,
- size limits,
- authorization,
- public access to uploaded files.

Dangerous signs:

- using original filename directly,
- extension blacklist instead of allowlist,
- storing uploads in web root,
- trusting `$_FILES["type"]`,
- missing authorization on download,
- processing archives without path checks.

## Deserialization review

Look for:

    unserialize($input)

and framework/session/cache code that may deserialize attacker-controlled data.

Risks:

- PHP object injection,
- gadget chains,
- magic methods:
  - `__wakeup`
  - `__destruct`
  - `__toString`
  - `__call`
  - `__callStatic`
  - `__get`
  - `__set`
  - `__invoke`

Check:

- `allowed_classes`,
- whether input is signed or MACed,
- whether Composer dependencies provide gadgets,
- whether serialized data comes from cookies, sessions, cache, database, or request parameters.

Do not claim exploitation without a gadget chain unless impact is still clear. A strong finding can be “unsafe deserialization of attacker-controlled data; gadget chain not yet validated.”

## Phar deserialization review

Phar archives carry serialized metadata that PHP unserializes when the
file is accessed via the `phar://` stream wrapper. This means filesystem
functions can become deserialization sinks if they accept attacker-controlled
paths.

Triggers include:

    file_exists($path)
    is_file($path)
    file_get_contents($path)
    fopen($path, "r")
    md5_file($path)
    filesize($path)
    stat($path)

When `$path` starts with `phar://` and points to an attacker-uploaded archive,
the metadata is unserialized — even if no `unserialize()` call appears in the
code. Pair file-upload findings with phar-reachability analysis.

Mitigations to verify:

- PHP version (Phar deserialization is restricted in PHP 8.0+ for some calls),
- explicit `Phar::interceptFileFuncs()` state,
- file-content/MIME validation on upload,
- storage outside any path that can be reflected back into a filesystem function.

## Type juggling and loose comparison review

PHP's `==`, `!=`, `in_array($x, $arr)` (without strict mode), and `switch`
statements use loose comparison and can be bypassed when attacker input is
compared to a value that coerces unexpectedly.

Classic patterns:

    if ($_POST["password"] == $stored)         // loose compare
    if (hash("sha256", $input) == $expected)   // magic hash
    if ($token == true)                        // any non-empty string passes
    in_array($value, $allowlist)               // missing strict=true
    switch ($input) { case 0: ... }            // string "abc" == 0 in PHP 7
    strcmp($a, $b) == 0                        // strcmp(array, ...) returns null

Magic hashes: strings whose hex hash starts with `0e` followed by digits are
interpreted as scientific notation `0` and equal each other under `==`.

Authentication bypass red flags:

- password comparison with `==` instead of `hash_equals`,
- token comparison with `==` instead of `hash_equals`,
- `strcmp` / `strpos` return value compared with `==` (returns false on type mismatch),
- `in_array` without strict mode on user-controlled input,
- JSON decoded values compared without type checks.

Safer patterns:

- `===` for sensitive comparisons,
- `hash_equals` for hash/token comparisons (timing-safe),
- `password_verify` for password verification,
- `in_array($x, $arr, true)` (strict mode),
- explicit type casts before comparison.

## XSS review

Look for user-controlled data reaching HTML, attributes, JavaScript, CSS, URLs, or templates.

Sources:

- request parameters,
- stored database content,
- uploaded filenames,
- profile fields,
- comments,
- admin-controlled-but-lower-trust content.

Sinks:

- `echo`,
- `print`,
- template output,
- inline scripts,
- HTML attributes,
- JSON embedded in HTML,
- markdown rendering.

Escaping functions:

    htmlspecialchars
    htmlentities
    json_encode
    urlencode

Check context. HTML escaping is not enough for every JavaScript, CSS, URL, or attribute context.

Framework template auto-escaping may mitigate XSS. Verify whether auto-escaping is enabled.

## CSRF review

Check state-changing routes using cookie-based authentication.

Risky operations:

- account changes,
- password/email changes,
- admin actions,
- file uploads,
- deletes,
- payments,
- configuration changes,
- webhook or integration setup.

Look for:

- CSRF token validation,
- SameSite cookie settings,
- framework middleware,
- method override behavior,
- JSON endpoints reachable by browser credentials,
- CORS interactions.

Do not report CSRF for pure bearer-token APIs unless browser credential behavior makes it relevant.

## Authentication review

Check:

- login flow,
- password verification,
- password hashing,
- remember-me cookies,
- password reset tokens,
- account activation,
- email change,
- MFA,
- session regeneration,
- logout,
- brute force protections,
- account enumeration,
- OAuth/OIDC/SAML integration.

Red flags:

- plain text passwords,
- weak hashes,
- missing `password_hash` / `password_verify`,
- predictable reset tokens,
- reset tokens not expiring,
- reset tokens reusable,
- no session regeneration after login,
- trusting client-controlled user id,
- missing email verification.

## Authorization review

Check:

- role checks,
- permission checks,
- object ownership,
- tenant isolation,
- admin-only routes,
- API endpoints,
- download endpoints,
- update/delete operations,
- hidden UI-only restrictions,
- direct script access.

Good finding example:

    `download.php?id=...` checks that the user is authenticated but loads the file
    by id and streams it without verifying ownership.

Bad finding example:

    The app might have IDOR issues.

## Session and cookie review

Check:

- session cookie flags:
  - HttpOnly,
  - Secure,
  - SameSite,
- session fixation,
- session id regeneration,
- logout invalidation,
- remember-me token storage,
- custom session handlers,
- session data trust assumptions,
- cookie signing/encryption.

## SSRF review

Look for user-controlled URLs reaching:

- `curl_exec`,
- `file_get_contents`,
- HTTP clients,
- webhook fetchers,
- image fetchers,
- PDF generators,
- URL previewers,
- import/export features.

Consider:

- redirects,
- DNS rebinding,
- internal IP ranges,
- localhost aliases,
- IPv6,
- cloud metadata endpoints,
- URL parser inconsistencies,
- alternate schemes.

## Open redirect review

Look for user-controlled redirect targets in:

    header("Location: " . $url)
    redirect($url)
    return redirect($request->input("next"))

Check allowlists, relative URL enforcement, and parser confusion.

## Mail header injection review

PHP's `mail()` accepts headers as a string parameter. User-controlled input
in `to`, `subject`, or the additional headers parameter without CRLF stripping
can inject arbitrary headers (BCC for spam relay, content-type for HTML
injection, MIME boundary tampering for attachment smuggling).

Dangerous patterns:

    mail($_POST["to"], "Subject", $body)
    mail($to, $_POST["subject"], $body)
    mail($to, $subject, $body, "From: " . $_POST["email"])

Check:

- CRLF (`\r`, `\n`, `%0a`, `%0d`) filtering on inputs that flow into headers,
- allowlist of recipient domains or hardcoded recipients for contact forms,
- use of `Symfony\Mailer`, `PHPMailer`, or `Laminas\Mail` (which validate
  addresses) versus raw `mail()`,
- additional headers parameter (5th arg) constructed from user input.

The 5th-argument escape mechanism in PHP 5.4+ does not validate header
content, only command-line escaping for the sendmail binary path.

## XML and XXE review

Look for:

    simplexml_load_string
    simplexml_load_file
    DOMDocument::loadXML
    DOMDocument::load
    XMLReader

Check whether external entity loading is possible, especially in older PHP/libxml configurations.

Consider:

- local file disclosure,
- SSRF,
- denial of service.

## Template injection review

Check template engines and dynamic template rendering.

Relevant engines:

- Twig,
- Blade,
- Smarty,
- custom template systems.

Look for:

- user-controlled template strings,
- user-controlled template filenames,
- unsafe filters,
- disabled escaping,
- raw output.

## Laravel-specific review

Look for:

- routes in `routes/web.php` and `routes/api.php`,
- controllers,
- middleware,
- policies,
- gates,
- request validation classes,
- Eloquent models,
- mass assignment settings,
- `$fillable`,
- `$guarded`,
- raw query usage,
- file storage usage,
- signed URLs,
- queue jobs,
- events/listeners,
- `APP_KEY`,
- debug mode,
- `.env` exposure.

Laravel red flags:

- `APP_DEBUG=true` in exposed environments,
- unsafe `unserialize`,
- `DB::raw` with request input,
- `whereRaw` / `orderByRaw` with request input,
- missing policies on model operations,
- mass assignment of sensitive fields,
- storing uploads under public path without validation.

## Symfony-specific review

Look for:

- routes,
- controllers,
- voters,
- access control config,
- security.yaml,
- form types,
- validators,
- Doctrine repositories,
- Twig templates,
- event subscribers,
- console commands.

Symfony red flags:

- missing voters for object-level authorization,
- raw DQL/SQL concatenation,
- unsafe Twig `raw`,
- weak access_control patterns,
- insecure remember-me config.

## WordPress-specific review

Look for:

- plugin/theme entrypoints,
- hooks:
  - `add_action`
  - `add_filter`,
- AJAX actions:
  - `wp_ajax_*`
  - `wp_ajax_nopriv_*`,
- REST API routes,
- shortcodes,
- admin pages,
- nonce checks,
- capability checks,
- `$wpdb` queries,
- file uploads,
- options updates.

WordPress red flags:

- missing `current_user_can`,
- missing `check_admin_referer` / `wp_verify_nonce`,
- unsafe `$wpdb->query` concatenation,
- missing `prepare`,
- unauthenticated AJAX actions,
- stored XSS in admin or public views,
- option update from request data.

## Drupal-specific review

Look for:

- route definitions,
- controllers,
- forms,
- permissions,
- access callbacks,
- entity access,
- render arrays,
- Twig templates,
- configuration forms.

Drupal red flags:

- missing access checks,
- unsafe render arrays,
- raw database queries with concatenation,
- unsafe file handling,
- bypassing entity access.

## Composer and dependency review

Check:

- `composer.json`,
- `composer.lock`,
- package versions,
- abandoned packages,
- autoload files,
- scripts section,
- post-install/update commands,
- path repositories,
- plugins.

Supply-chain red flags:

- unpinned or overly broad constraints,
- risky Composer scripts,
- abandoned packages,
- dev dependencies used in production,
- insecure package versions.

Do not invent CVEs without verification. If current vulnerability data is needed, use external up-to-date sources outside this skill.

## Secrets and configuration

Check:

- `.env`,
- `.env.example`,
- config files,
- hardcoded credentials,
- API keys,
- database passwords,
- private keys,
- JWT secrets,
- encryption keys,
- debug flags,
- exposed backups.

Do not include real secrets in findings or reports. Mask values.

### Error reporting and information disclosure

PHP error output frequently leaks paths, query fragments, stack traces,
class names, and configuration details that aid further attacks.

Check:

- `display_errors` (should be `Off` in production),
- `display_startup_errors`,
- `error_reporting` level,
- custom error handlers that echo or render the exception,
- framework debug flags:
  - Laravel `APP_DEBUG=true`,
  - Symfony `APP_ENV=dev` / `APP_DEBUG=1`,
  - WordPress `WP_DEBUG`, `WP_DEBUG_DISPLAY`,
- `phpinfo()` exposure,
- exception messages echoed back to the client,
- stack traces in JSON API responses,
- `.git/`, `.env`, `composer.lock`, backup files reachable via web server.

## Validation methods

Useful validation methods for PHP targets include:

- local HTTP requests,
- framework integration tests,
- PHP built-in server for simple apps,
- Docker Compose app stack,
- CLI script execution,
- crafted request bodies,
- crafted uploaded files,
- two-user / two-tenant tests,
- database fixture tests,
- static proof for missing authorization,
- log inspection,
- PHPUnit tests,
- Psalm/PHPStan-assisted review when available.

## Evidence to capture

For confirmed PHP findings, capture:

- request,
- response,
- route or script path,
- authentication context,
- user/tenant ids,
- relevant logs,
- database state if needed,
- uploaded/generated files if relevant,
- exact command or HTTP request,
- expected safe behavior,
- observed vulnerable behavior.

Do not include real secrets.

## Counter-analysis checklist

Before keeping a PHP finding open, check:

- Is input actually attacker-controlled?
- Is the script/route reachable?
- Is authentication required?
- Is authorization enforced by framework middleware, policy, voter, guard, hook, or explicit check?
- Is input validation applied?
- Is output escaping context-correct?
- Is SQL parameterized or allowlisted?
- Is filesystem access constrained to a safe base directory?
- Is upload storage safe?
- Is deserialization input signed or restricted?
- Is CSRF protection enabled?
- Is the code test-only, migration-only, or dev-only?
- Is the issue duplicated elsewhere?

## Reporting guidance

Be precise.

Mention:

- route, script, controller, hook, or command,
- affected role/user/tenant,
- attacker-controlled input,
- missing or insufficient control,
- dangerous sink,
- realistic impact,
- validation method,
- evidence path.

Avoid broad claims such as:

    The PHP app has SQL injection.

Prefer:

    `$_GET["sort"]` reaches `ORDER BY $sort` in `UserRepository::search()`
    without allowlisting column names or sort direction, allowing SQL injection
    through the `sort` query parameter.

## Completion checklist

Before creating or keeping a PHP finding:

- affected PHP file or route is identified,
- attacker-controlled input is identified,
- dangerous sink or missing security decision is identified,
- framework/CMS protections were considered,
- realistic impact is explained,
- validation plan is actionable,
- counter-analysis is included,
- evidence requirements are clear.
