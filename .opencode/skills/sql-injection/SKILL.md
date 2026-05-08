# SQL Injection Skill

Use this skill when reviewing code that builds, executes, transforms, or indirectly influences SQL queries.

This skill applies to any language, framework, ORM, query builder, repository layer, stored procedure wrapper, migration tooling, reporting module, search/filter system, or data access abstraction where attacker-controlled input may affect SQL execution.

This skill supports reconnaissance, vulnerability hypothesis generation, counter-analysis, validation, and reporting.

## Scope

Use this skill for targets that interact with SQL databases such as:

- PostgreSQL
- MySQL / MariaDB
- SQL Server
- Oracle
- SQLite
- DB2
- H2
- HSQLDB
- CockroachDB
- YugabyteDB
- cloud SQL-compatible services

Relevant code areas include:

- repositories,
- DAOs,
- services with direct DB access,
- ORM queries,
- raw SQL helpers,
- search/filter builders,
- reporting/export queries,
- admin dashboards,
- analytics queries,
- migration scripts,
- stored procedure callers,
- dynamic SQL generation,
- multi-tenant filters,
- authorization filters expressed in SQL,
- data import/export tools,
- CLI maintenance tools.

### Out of scope

This skill does not cover NoSQL injection. For MongoDB, Redis, Cassandra,
DynamoDB, Elasticsearch, CouchDB, or other non-SQL stores, use a dedicated
skill or generic input-validation analysis. The injection model, query
syntax, and parameterization primitives differ enough that conflating them
produces poor-quality findings.

## Primary objective

Find SQL injection only when there is a credible path where attacker-controlled or externally influenced data changes SQL syntax or semantics in an unsafe way.

Do not report SQL injection merely because:

- SQL exists,
- raw SQL exists,
- an ORM is used,
- string interpolation exists in a non-query context,
- a value reaches a parameterized query,
- input reaches an allowlisted query builder,
- the filename contains “sql”,
- a scanner keyword matched.

A valid SQL injection finding must show:

1. attacker-controlled or externally influenced input,
2. propagation to query construction,
3. unsafe SQL syntax influence,
4. missing or insufficient parameterization / allowlisting / validation,
5. reachable execution path,
6. realistic impact,
7. validation plan.

## Common attacker-controlled sources

Track data from:

- HTTP query parameters,
- HTTP route parameters,
- HTTP request body fields,
- form fields,
- JSON payloads,
- GraphQL arguments,
- RPC parameters,
- CLI arguments,
- stdin,
- config files controlled by lower-trust users,
- uploaded files,
- imported CSV/Excel/XML/JSON data,
- webhook payloads,
- queue messages,
- environment variables in lower-trust deployments,
- cookies,
- headers,
- session values influenced by users,
- database fields previously controlled by users,
- tenant/user/profile preferences,
- saved filters,
- report definitions,
- sort/group/search configuration,
- admin UI inputs if lower-trust admins exist.

Consider second-order SQL injection where data is stored safely first, then later used unsafely to build SQL.

## Dangerous sinks

Review input reaching:

- raw SQL execution,
- dynamic SQL construction,
- raw fragments in ORMs,
- raw fragments in query builders,
- dynamic `WHERE`,
- dynamic `ORDER BY`,
- dynamic `GROUP BY`,
- dynamic `HAVING`,
- dynamic `LIMIT` / `OFFSET`,
- dynamic table names,
- dynamic column names,
- dynamic schema names,
- dynamic database names,
- dynamic join conditions,
- dynamic operators,
- dynamic sort direction,
- dynamic stored procedure names,
- dynamic function names,
- dynamic JSON path expressions,
- dynamic full-text search expressions,
- dynamic `LIKE` patterns when escaping is wrong,
- dynamic `IN (...)` list construction,
- dynamic bulk insert/update statements,
- dynamic migration scripts,
- dynamic report SQL,
- dynamic row-level security predicates,
- tenant filters.

## High-risk SQL patterns

Look for:

    "SELECT ... " + userInput
    $"SELECT ... {userInput}"
    string.Format("SELECT ... {0}", userInput)
    query += request["..."]
    raw("... " + input)
    whereRaw(input)
    orderByRaw(input)
    groupByRaw(input)
    havingRaw(input)
    FromSqlRaw(...)
    ExecuteSqlRaw(...)
    createNativeQuery(...)
    createSQLQuery(...)
    connection.createStatement().execute(...)
    cursor.execute("... %s" % value)
    db.Query("... " + value)
    sequelize.literal(input)
    knex.raw(input)
    prisma.$queryRawUnsafe(input)
    mysqli_query($conn, "... " . $_GET["id"])
    $pdo->query("... $id")
    DB::raw($request->input("field"))

Do not report solely on the API name. Confirm attacker control and unsafe query influence.

## Safer patterns

Usually safer:

- prepared statements with bound parameters,
- ORM parameter binding,
- query builder value binding,
- stored procedures with parameters,
- `FromSqlInterpolated` in EF Core,
- `?` placeholders,
- named placeholders,
- allowlisted identifiers,
- fixed enum-based sort fields,
- fixed enum-based sort directions,
- server-side mapping from user option to SQL fragment,
- strongly typed expressions that do not expose raw SQL.

Still review safer patterns carefully when:

- identifiers are dynamic,
- raw fragments are mixed with parameters,
- stored procedures build dynamic SQL internally,
- allowlists are incomplete or bypassable,
- data type conversion happens after concatenation,
- SQL syntax is affected by user input.

## Important distinction: values vs identifiers

Parameterized queries protect values, not SQL identifiers.

Usually safe value parameter:

    WHERE id = @id

Potentially unsafe identifier:

    ORDER BY {userControlledColumn}

Potentially unsafe direction:

    ORDER BY name {userControlledDirection}

Potentially unsafe table:

    SELECT * FROM {userControlledTable}

For identifiers, require strict allowlisting or server-side mapping.

Good pattern:

    allowed = {
      "name": "users.name",
      "created": "users.created_at"
    }
    column = allowed[user_sort_key]
    sql = "ORDER BY " + column

Bad pattern:

    sql = "ORDER BY " + request["sort"]

## Query parts that often cannot be parameterized directly

Review carefully:

- table name,
- column name,
- schema name,
- database name,
- sort direction,
- operator,
- SQL keyword,
- function name,
- collation,
- index hint,
- JSON path,
- full-text search mode,
- `LIMIT` and `OFFSET` in some drivers,
- `IN` list expansion in some APIs,
- raw `WHERE` fragments,
- raw `ORDER BY` fragments.

These usually require allowlisting, safe expansion, or framework-specific helper APIs.

## Common SQL injection variants

### Classic string concatenation

User input is concatenated into SQL.

Example vulnerable pattern:

    sql = "SELECT * FROM users WHERE name = '" + name + "'"

Look for direct or indirect concatenation.

### Numeric injection

Code assumes numeric input is safe.

Example vulnerable pattern:

    sql = "SELECT * FROM users WHERE id = " + id

Check whether the value is strongly parsed before query construction.

### Identifier injection

User controls table, column, schema, sort key, group key, or alias.

Example vulnerable pattern:

    sql = "ORDER BY " + sort

This is common in search APIs and reporting modules.

Note that `UNION` statements cannot be used directly inside an `ORDER BY` clause.
Data extraction from an `ORDER BY` injection must usually rely on boolean
inference, forcing the application to sort differently based on the truth of a
guessed condition.

Example blind-extraction payload:

    (CASE WHEN (SUBSTRING(version(),1,1)='5') THEN column_a ELSE column_b END)

If the app sorts by `column_a`, the condition is true; if by `column_b`, false.

#### Mass-assignment-driven identifier injection

Some frameworks let attackers control which model attributes get persisted,
which in turn controls which columns appear in the generated SQL. Even when
values are safely parameterized, the *target column* itself is attacker-chosen.

Affected APIs (when used without explicit allowlists):

- Eloquent / Laravel: `Model::fill($request->all())`, `Model::create($input)`
  with weak `$fillable` / `$guarded`,
- ActiveRecord / Rails: `Model.update_attributes(params[:user])` without
  strong parameters,
- Django: `Model(**request.POST)` or `ModelForm` with broad `fields`,
- EF Core: `TryUpdateModelAsync(model)` without `includeProperties`,
- Sequelize / Mongoose-on-SQL bridges with permissive allow-listing.

Impact often crosses with mass-assignment: privilege escalation by setting
`is_admin`, tenant escape by setting `tenant_id`, integrity loss by writing
columns the UI never exposes. The SQL is technically parameterized, but the
*shape* of the `UPDATE ... SET ...` (or `INSERT INTO ... (cols) VALUES ...`)
is attacker-chosen.

Treat this as SQL-adjacent: report under SQL-injection only when the impact
hinges on the SQL identifier surface; otherwise prefer a mass-assignment
finding.

### Boolean-based injection

User input changes predicates.

Example:

    id=1 OR 1=1

### UNION-based injection

User input allows `UNION SELECT`.

Relevant when query result is returned to caller.

### Error-based injection

Database errors expose injection behavior.

Useful validation signal, but avoid relying on production error messages.

### Time-based blind injection

User input can trigger delay functions.

Examples:

- PostgreSQL: `pg_sleep`
- MySQL: `SLEEP`
- SQL Server: `WAITFOR DELAY`

Use only in local sandbox validation.

### Stacked queries

User input allows multiple statements.

Depends heavily on driver/database settings.

Examples:

    1; DROP TABLE users

Check whether the driver allows multiple statements.

### Second-order injection

Input is stored first, then later used unsafely in SQL.

Example:

    saved report sort expression
    saved custom field name
    saved filter condition

### LIKE injection

Not always SQL injection, but may cause wildcard injection, data exposure, or search bypass.

Review escaping of:

- `%`
- `_`
- escape character

### Full-text search injection

User input influences full-text query syntax.

Examples:

- PostgreSQL `to_tsquery`
- MySQL boolean full-text mode
- SQL Server full-text predicates

May cause syntax injection, logic bypass, or error-based leakage.

### JSON / XML path injection

User input influences JSON path, XPath-like SQL functions, or XML query functions.

Examples:

- PostgreSQL JSON path
- MySQL JSON path
- SQL Server JSON functions
- Oracle XML/JSON functions

### Stored procedure dynamic SQL

Calling stored procedures with parameters is not automatically safe if the procedure builds dynamic SQL internally.

Look for:

- `EXEC`
- `sp_executesql`
- `EXECUTE IMMEDIATE`
- `PREPARE`
- `format`
- concatenated dynamic statements inside procedures.

## Language and framework patterns

### PHP

Dangerous:

    mysqli_query($conn, "SELECT ... " . $_GET["id"])
    $pdo->query("SELECT ... $id")
    DB::raw($request->input("field"))
    whereRaw($input)
    orderByRaw($input)

Safer:

    PDO prepared statements
    mysqli prepared statements
    Laravel query builder with bindings
    Eloquent with parameterized conditions

Still review raw expressions and dynamic identifiers.

### Python

Dangerous:

    cursor.execute("SELECT ... %s" % value)
    cursor.execute(f"SELECT ... {value}")
    cursor.execute("SELECT ... " + value)
    text(f"SELECT ... {value}")

Safer:

    cursor.execute("SELECT ... WHERE id = %s", (value,))
    SQLAlchemy bound parameters
    Django ORM filters

SQLAlchemy `text()` is safe when used with named bind parameters, not when
the SQL string itself is built by interpolation:

    # Safe: parameterized via bindparams
    stmt = text("SELECT ... WHERE id = :id")
    conn.execute(stmt, {"id": user_id})

    # Unsafe: string was already interpolated before text() saw it
    stmt = text(f"SELECT ... WHERE id = {user_id}")

Review:

- SQLAlchemy `text`,
- `literal_column`,
- raw SQL,
- Django `.raw`,
- `.extra`,
- custom managers,
- dynamic `order_by`.

### Java / Kotlin

Dangerous:

    Statement.execute(query)
    createNativeQuery("..." + input)
    jdbcTemplate.query("..." + input)
    entityManager.createQuery("..." + input)

Safer:

    PreparedStatement
    named parameters
    JPA parameters
    jOOQ DSL with bindings

Review:

- dynamic JPQL/HQL,
- Criteria API with raw fragments,
- MyBatis `${}` vs `#{}`,
- dynamic XML mapper fragments.

### C# / .NET

Dangerous:

    FromSqlRaw(...)
    ExecuteSqlRaw(...)
    SqlQueryRaw(...)
    "SELECT ... " + input
    string interpolation into SQL strings
    NHibernate CreateSQLQuery with concatenation
    HQL concatenation
    Dapper with interpolated raw SQL

Safer:

    FromSqlInterpolated(...)
    parameterized SqlCommand
    Dapper parameters
    EF LINQ queries
    NHibernate named parameters

Review:

- dynamic `ORDER BY`,
- raw SQL fragments,
- property names from users,
- tenant filters,
- report builders.

### JavaScript / TypeScript

Dangerous:

    sequelize.query("..." + input)
    sequelize.literal(input)
    knex.raw(input)
    prisma.$queryRawUnsafe(input)
    db.query(`SELECT ... ${input}`)
    mysql.query("..." + input)

Safer:

    parameterized queries,
    Prisma query API,
    Prisma `$queryRaw` tagged templates,
    Knex query builder with bindings,
    Sequelize replacements/bind parameters.

Review dynamic identifiers and raw fragments.

### Go

Dangerous:

    db.Query("SELECT ... " + input)
    fmt.Sprintf("SELECT ... %s", input)
    raw SQL builders with user input

Safer:

    db.Query("SELECT ... WHERE id = ?", id)
    sqlc-generated queries,
    squirrel/goqu with bindings when used correctly.

Review dynamic identifiers and query fragments.

### Ruby

Dangerous:

    where("name = '#{name}'")
    find_by_sql("..." + input)
    order(params[:sort])
    Arel.sql(params[:fragment])

Safer:

    parameterized `where`,
    ActiveRecord hash conditions,
    allowlisted order fields.

Review raw SQL fragments and dynamic ordering.

## ORM-specific issues

Do not assume ORM means safe.

Review:

- raw query APIs,
- native SQL APIs,
- raw fragments,
- dynamic order/group clauses,
- dynamic table/column names,
- string-built HQL/JPQL/DQL,
- custom query builders,
- report engines,
- search filters,
- tenant filters,
- soft-delete filters,
- row-level authorization filters.

## MyBatis-specific note

In MyBatis:

    #{param}

usually binds as a parameter.

    ${param}

performs string substitution and can be dangerous.

Review `${}` carefully, especially in:

- `ORDER BY`,
- table names,
- column names,
- dynamic `WHERE`.

## Dapper-specific note

Dapper parameters are safe when used as parameters:

    connection.Query("SELECT * FROM Users WHERE Id = @Id", new { Id = id })

But string interpolation before passing to Dapper is not safe:

    connection.Query($"SELECT * FROM Users WHERE Id = {id}")

Dynamic identifiers still require allowlisting.

## Entity Framework Core-specific note

Review:

- `FromSqlRaw`
- `ExecuteSqlRaw`
- `SqlQueryRaw`
- raw fragments mixed with interpolation
- dynamic `OrderBy` helpers
- raw SQL report queries.

`FromSqlInterpolated` is generally safer for values, but not for identifiers.

## NHibernate-specific note

Review:

- `CreateSQLQuery`
- `CreateQuery`
- HQL string concatenation,
- dynamic filters,
- dynamic sorting,
- property names,
- aliases,
- raw SQL fragments.

Named parameters help values, not identifiers.

## PostgreSQL-specific notes

Review dynamic use of:

- `format`
- `EXECUTE`
- `quote_ident`
- `quote_literal`
- `to_tsquery`
- JSON path functions,
- `COPY`,
- `dblink`,
- `postgres_fdw`,
- `search_path`,
- row-level security predicates.

Dynamic SQL in PL/pgSQL can be vulnerable if user input reaches `EXECUTE`.

Safe dynamic identifiers should use `quote_ident` or `format('%I', identifier)` with allowlisting when possible.

## MySQL/MariaDB-specific notes

Review:

- multiple statements setting,
- `PREPARE` / `EXECUTE`,
- dynamic SQL in stored routines,
- `LOAD DATA`,
- `INTO OUTFILE`,
- boolean full-text mode,
- `SLEEP`,
- identifier quoting with backticks,
- character set escaping issues.

### Character set / multibyte escape bypass

Naive escaping (`mysql_real_escape_string`, generic `addslashes`-style
helpers, or PDO with emulated prepares) can be bypassed when the
connection charset and the server charset disagree.

Classic example (GBK / Big5 / SJIS connections):

    Input bytes: 0xbf 0x27
    After backslash escape:    0xbf 0x5c 0x27
    Interpreted under GBK as:  ¿\  + '
    Result: the trailing quote is no longer escaped.

Indicators:

- `mysql_real_escape_string` used without explicit `mysql_set_charset` or
  `SET NAMES` to a sane multibyte-safe encoding,
- `SET NAMES` used instead of `mysql_set_charset` (does not update the
  client API's charset awareness, so escapes are computed wrong),
- legacy code paths or libraries running before charset is set,
- emulated prepared statements with multibyte client charsets.

Prefer real (server-side) prepared statements with parameter binding,
and pin the connection charset to `utf8mb4`.

### Prepared-statement emulation gotcha

PHP's PDO MySQL driver emulates prepared statements client-side by default
(`PDO::ATTR_EMULATE_PREPARES = true` historically). Emulation:

- performs string substitution in the client library,
- is sensitive to the charset bypass above,
- can mis-handle some edge cases (multi-byte, binary data),
- silently allows multiple statements when stacked queries are otherwise
  blocked.

Verify whether emulation is on or off, and prefer
`PDO::ATTR_EMULATE_PREPARES => false` together with `utf8mb4`.

Other drivers (e.g., some Go MySQL drivers, legacy mysqli paths) have
similar emulation switches; check driver configuration during recon.

## SQL Server-specific notes

Review:

- `EXEC`
- `sp_executesql`
- dynamic SQL in stored procedures,
- `QUOTENAME`,
- `WAITFOR DELAY`,
- `xp_cmdshell`,
- linked servers,
- ownership chaining,
- dynamic `ORDER BY`.

Using `sp_executesql` helps only when values are parameters, not concatenated into the SQL string.

## Oracle-specific notes

Review:

- `EXECUTE IMMEDIATE`,
- dynamic PL/SQL blocks,
- `DBMS_SQL`,
- `DBMS_ASSERT`,
- dynamic object names,
- XML/JSON functions,
- external tables.

## SQLite-specific notes

Review:

- local CLI/tool contexts,
- file path control,
- attached databases,
- extension loading,
- dynamic SQL in desktop apps or local tools.

SQLite injection can still be security-relevant if it affects data integrity, local file access, auth checks, or application behavior.

## Reconnaissance checklist

During reconnaissance, identify:

- database type,
- DB access libraries,
- ORM/query builder,
- raw SQL files,
- repository/DAO layer,
- search/filter/report builders,
- migrations and stored procedures,
- tenant filters,
- authorization filters in queries,
- dynamic sorting and paging,
- import/export SQL,
- admin dashboards,
- logging of SQL errors,
- test database setup,
- validation methods.

Useful search patterns:

    rg -n "SELECT|INSERT|UPDATE|DELETE|WHERE|ORDER BY|GROUP BY|HAVING|FROM" src
    rg -n "raw|Raw|query|Query|execute|Execute|createSQL|createQuery|FromSql|SqlQuery" src
    rg -n "orderBy|OrderBy|sort|Sort|filter|Filter|search|Search" src
    rg -n "prepare|PreparedStatement|bind|parameter|SqlParameter" src

Do not rely only on grep. Use it to find review candidates.

## Hypothesis generation checklist

Before creating a SQL injection finding, confirm:

- source input is controlled or influenced by attacker,
- input reaches SQL construction,
- input affects SQL syntax or semantics,
- parameter binding is missing or insufficient,
- allowlisting is missing or bypassable,
- query execution is reachable,
- impact is realistic,
- validation plan is actionable.

## Counter-analysis checklist

Before keeping a finding open, check:

- Is the input actually attacker-controlled?
- Is input parsed to a safe type before query construction?
- Is the query parameterized?
- Is the ORM binding values safely?
- Is the dynamic part only an allowlisted identifier?
- Is sort direction allowlisted?
- Is table/column mapping server-side only?
- Is the reported raw SQL actually constant?
- Is the dangerous path reachable?
- Is this admin-only, and does that still matter?
- Is authorization enforced elsewhere?
- Is the issue a duplicate?
- Is the finding confusing SQL injection with wildcard search behavior?
- Is the query built but never executed?
- Is the code test-only or migration-only?
- Is the vulnerable code behind a trusted internal-only boundary?

## Validation methods

Useful validation methods include:

- unit test around query builder,
- integration test against local database,
- HTTP request against local service,
- CLI invocation with payload,
- crafted import file,
- static proof,
- database log inspection,
- SQL error observation,
- boolean-based payload,
- time-based payload in local sandbox,
- `UNION` payload in local sandbox,
- second-order setup then trigger.

Prefer non-destructive payloads.

Do not run destructive SQL payloads unless the sandbox is disposable and the validation specifically requires it.

## Safe local validation payload examples

Use only in local sandbox.

Boolean probe examples:

    ' OR '1'='1
    ' OR 1=1 --
    1 OR 1=1
    1) OR (1=1 --

Error probe examples:

    '
    "
    1'
    1"

Order-by probe examples:

    name
    name DESC
    name; SELECT 1 --
    CASE WHEN 1=1 THEN name ELSE id END

Time-based examples:

PostgreSQL:

    ' OR pg_sleep(1) IS NULL --

MySQL:

    ' OR SLEEP(1) --

SQL Server:

    '; WAITFOR DELAY '00:00:01' --

Use short delays and only in local sandbox.

## Validation evidence

Capture:

- exact request/command/input,
- affected parameter,
- generated SQL if available,
- database error or behavioral difference,
- query logs,
- application logs,
- response difference,
- timing difference,
- test output,
- database state before/after if relevant,
- expected safe behavior,
- observed vulnerable behavior.

Do not include real secrets or production data.

## Confirmation policy

A SQL injection finding may be marked `CONFIRMED` when evidence clearly shows that attacker-controlled input changes SQL syntax or semantics unsafely.

Strong confirmation examples:

- payload changes query result set,
- payload bypasses intended filter,
- payload triggers database syntax error at injection point,
- payload triggers local time delay,
- payload demonstrates UNION extraction in sandbox,
- generated SQL clearly includes unescaped attacker-controlled syntax,
- unit/integration test proves unsafe query construction and execution,
- strong static proof shows reachable unsafe concatenation into executed SQL.

Weak evidence not enough by itself:

- raw SQL exists,
- string concatenation exists but input is constant,
- user input reaches a bound parameter,
- query builder uses safe API,
- generic scanner warning,
- filename says SQL,
- comments mention injection,
- wildcard search broadens results but SQL syntax is not controlled.

## Rejection policy

Reject when:

- data is bound as a parameter,
- input is strongly parsed before query construction,
- dynamic identifiers are allowlisted,
- sort direction is allowlisted,
- attacker cannot influence the value,
- code path is unreachable,
- query is never executed,
- input affects only data values safely,
- the issue is only wildcard search behavior without SQL syntax control,
- the report relies only on generic raw SQL usage,
- the issue is duplicate.

## Severity guidance

Severity depends on impact.

Consider:

- unauthenticated vs authenticated,
- low-privilege vs admin-only,
- tenant boundary impact,
- data confidentiality,
- data integrity,
- authentication bypass,
- authorization bypass,
- stacked queries allowed,
- file read/write primitives,
- RCE via DB-specific features,
- database permissions,
- error visibility,
- exploitability.

Possible severity examples:

- CRITICAL: unauthenticated injection leading to RCE or full data compromise.
  Common DB-RCE primitives include SQL Server `xp_cmdshell`, PostgreSQL
  `COPY ... FROM PROGRAM` and untrusted PL/Perl/PL/Python languages,
  MySQL `INTO OUTFILE` chained with web-root file write, and Oracle
  `DBMS_SCHEDULER` / `DBMS_JAVA` abuse. Severity also reaches CRITICAL on
  full data compromise via UNION extraction or OOB exfiltration without RCE.
- HIGH: authenticated low-privilege injection exposing cross-tenant sensitive data.
- MEDIUM: limited injection in admin-only reporting feature with meaningful data exposure.
- LOW: local CLI injection in trusted maintenance tool with limited security impact.
- INFO: unsafe-looking pattern not reachable by untrusted input.

Do not overstate severity without validation.

## Reporting guidance

A good SQL injection report includes:

- affected endpoint/command/function,
- affected parameter,
- source of attacker input,
- sink/query construction point,
- unsafe SQL fragment,
- why parameterization/allowlisting is insufficient,
- realistic impact,
- validation method,
- evidence files,
- remediation idea.

Good wording:

    The `sort` query parameter reaches `ORDER BY ${sort}` in
    `ReportRepository.buildQuery()` without allowlisting. Because SQL
    identifiers cannot be safely parameterized through the current API, the
    code must map user-visible sort keys to fixed server-side column names.

Bad wording:

    This app uses SQL strings, so it has SQL injection.

## Remediation guidance

Prefer:

- prepared statements,
- bound parameters,
- ORM parameter binding,
- query builder safe APIs,
- allowlisted identifiers,
- server-side mapping of sort keys,
- enum-based sort directions,
- safe `IN` list expansion,
- safe stored procedure parameters,
- removal of raw SQL fragments,
- centralized query builder helpers,
- tests for malicious inputs.

For dynamic identifiers:

- never pass raw user strings directly,
- map user options to fixed SQL identifiers,
- validate against strict allowlists,
- quote identifiers correctly only after allowlisting.

For stored procedures:

- parameterize values,
- avoid dynamic SQL,
- if dynamic SQL is required, use safe identifier quoting and allowlists,
- avoid concatenating values into dynamic statements.

## Completion checklist

Before creating or keeping a SQL injection finding:

- affected query construction point is identified,
- executed SQL sink is identified,
- attacker-controlled input is identified,
- unsafe SQL syntax influence is explained,
- safe parameterization was checked,
- allowlisting was checked,
- reachability was checked,
- impact is realistic,
- validation plan is actionable,
- counter-analysis is included,
- evidence requirements are clear.

## Companion skills

This skill is cross-language and focused on a single vulnerability class.
When the target also matches a language-specific or framework-specific
skill, apply both: this skill provides the SQL injection lens, and the
language skill provides framework, runtime, and ecosystem context.

Frequent combinations:

- `.opencode/skills/php-security/` for PHP / Laravel / Symfony / WordPress / Drupal,
- `.opencode/skills/dotnet-security/` for ASP.NET / EF Core / Dapper / NHibernate,
- `.opencode/skills/web-security/` for HTTP-layer attacker control and routing,
- `.opencode/skills/c-cpp-security/` for native code linking against
  client libraries (libpq, libmysqlclient, sqlite3) where memory-safety
  issues may compound SQL handling.
