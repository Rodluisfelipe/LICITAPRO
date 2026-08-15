-- =========================================================================
-- Extensiones y objetos que Django no genera solo.
-- Ejecutar en una RunSQL dentro de la primera migración.
-- =========================================================================

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- autocompletado de entidades
CREATE EXTENSION IF NOT EXISTS unaccent;    -- búsqueda sin tildes


-- -------------------------------------------------------------------------
-- Configuración FTS en español SIN tildes.
-- "garantías" y "garantias" deben ser el mismo término.
-- -------------------------------------------------------------------------
CREATE TEXT SEARCH CONFIGURATION es_unaccent (COPY = spanish);

ALTER TEXT SEARCH CONFIGURATION es_unaccent
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, spanish_stem;


-- -------------------------------------------------------------------------
-- Trigger: mantiene search_vector al día en los fragmentos.
-- Peso A al título de sección, B al cuerpo: un match en el encabezado
-- ("REQUISITOS FINANCIEROS") pesa más que uno en el párrafo.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fragmento_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('es_unaccent', coalesce(NEW.titulo_seccion, '')), 'A') ||
        setweight(to_tsvector('es_unaccent', coalesce(NEW.numeral, '')),        'A') ||
        setweight(to_tsvector('es_unaccent', coalesce(NEW.texto, '')),          'B');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fragmento_tsv
    BEFORE INSERT OR UPDATE OF texto, titulo_seccion, numeral
    ON documentos_fragmentodocumento
    FOR EACH ROW EXECUTE FUNCTION fragmento_tsv_update();


-- -------------------------------------------------------------------------
-- Búsqueda híbrida con Reciprocal Rank Fusion.
--
-- Por qué híbrida y no solo vectorial: los pliegos están llenos de literales
-- que un embedding denso no distingue — "numeral 3.2.1", códigos UNSPSC,
-- NITs, "Decreto 1082". El BM25 los encuentra exacto; el vector encuentra
-- lo semántico. RRF los fusiona sin tener que calibrar pesos.
--
-- k=60 es el valor estándar de la literatura de RRF.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION buscar_fragmentos(
    p_proceso_id  uuid,
    p_consulta    text,
    p_embedding   vector(1024),
    p_limite      int DEFAULT 20
)
RETURNS TABLE (
    fragmento_id bigint,
    pagina       int,
    numeral      varchar,
    texto        text,
    score        double precision
) AS $$
WITH lexica AS (
    SELECT f.id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(f.search_vector,
                                   websearch_to_tsquery('es_unaccent', p_consulta)) DESC
           ) AS rango
    FROM documentos_fragmentodocumento f
    WHERE f.proceso_id = p_proceso_id
      AND f.search_vector @@ websearch_to_tsquery('es_unaccent', p_consulta)
    LIMIT 60
),
semantica AS (
    SELECT f.id,
           ROW_NUMBER() OVER (ORDER BY f.embedding <=> p_embedding) AS rango
    FROM documentos_fragmentodocumento f
    WHERE f.proceso_id = p_proceso_id
      AND f.embedding IS NOT NULL
    ORDER BY f.embedding <=> p_embedding
    LIMIT 60
)
SELECT f.id,
       f.pagina,
       f.numeral,
       f.texto,
       COALESCE(1.0 / (60 + l.rango), 0.0) +
       COALESCE(1.0 / (60 + s.rango), 0.0) AS score
FROM documentos_fragmentodocumento f
LEFT JOIN lexica    l ON l.id = f.id
LEFT JOIN semantica s ON s.id = f.id
WHERE l.id IS NOT NULL OR s.id IS NOT NULL
ORDER BY score DESC
LIMIT p_limite;
$$ LANGUAGE sql STABLE;


-- -------------------------------------------------------------------------
-- Índice trigram para el autocompletado de entidades (ya declarado en el
-- modelo, aquí por referencia). Consulta típica:
--
--   SELECT * FROM core_entidad
--   WHERE nombre_normalizado % unaccent(lower('alcaldia de chia'))
--   ORDER BY similarity(nombre_normalizado, unaccent(lower('alcaldia de chia'))) DESC
--   LIMIT 10;
-- -------------------------------------------------------------------------
