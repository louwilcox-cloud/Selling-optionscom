--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (84ade85)
-- Dumped by pg_dump version 16.9

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_users; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.admin_users (
    user_id integer NOT NULL,
    granted_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.admin_users OWNER TO neondb_owner;

--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.user_sessions (
    session_id character varying(255) NOT NULL,
    user_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL,
    ip_address character varying(45),
    user_agent text
);


ALTER TABLE public.user_sessions OWNER TO neondb_owner;

--
-- Name: users; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_login timestamp without time zone,
    is_active boolean DEFAULT true,
    login_count integer DEFAULT 0
);


ALTER TABLE public.users OWNER TO neondb_owner;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO neondb_owner;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: neondb_owner
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: watchlists; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.watchlists (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    symbols text NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.watchlists OWNER TO neondb_owner;

--
-- Name: watchlists_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

CREATE SEQUENCE public.watchlists_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.watchlists_id_seq OWNER TO neondb_owner;

--
-- Name: watchlists_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: neondb_owner
--

ALTER SEQUENCE public.watchlists_id_seq OWNED BY public.watchlists.id;


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: watchlists id; Type: DEFAULT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.watchlists ALTER COLUMN id SET DEFAULT nextval('public.watchlists_id_seq'::regclass);


--
-- Data for Name: admin_users; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.admin_users (user_id, granted_at) FROM stdin;
1	2025-09-04 20:11:37.764424
3	2025-09-05 12:34:18.576005
6	2025-09-07 16:11:13.712103
2	2025-09-07 23:36:45.898056
\.


--
-- Data for Name: user_sessions; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.user_sessions (session_id, user_id, created_at, expires_at, ip_address, user_agent) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.users (id, email, password_hash, created_at, last_login, is_active, login_count) FROM stdin;
2	twilcox811@gmail.com	$2b$12$EXTvre2srEQrRr.RAXVFtuMgpDywRs4L91oBaePIsYHCSAUa2H.Xq	2025-09-04 20:27:21.912853	2025-09-05 14:26:43.744339	t	21
1	lou.wilcox@gmail.com	$2b$12$NHHsNYgxzGQPshY0SLUF2O1hFlBoLYqVGEsFI6IH9.8sPZiHXEJmq	2025-09-04 20:09:46.11136	2025-09-06 19:06:28.837352	t	45
6	admin@selling-options.com	$2b$12$sZEAXSIVTelCnIl6sKIgeONa3OeXPLwfQ0D.PrR0CDQskNMy52agK	2025-09-07 14:38:26.083534	\N	t	0
3	admin@lab.com	$2b$12$nEstcau1g0KPJME/fqeQkOT..VqFxrjXPR6c24vGA2mYCcZ3rGvkO	2025-09-05 12:34:12.999652	2025-09-05 12:34:56.760991	t	2
\.


--
-- Data for Name: watchlists; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.watchlists (id, name, symbols, created_by, created_at, updated_at) FROM stdin;
1	MAG 7	AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA	1	2025-09-04 23:04:18.837873	2025-09-04 23:04:18.837873
2	Index	XLE, XLK, XLV, SPY, QQQ, IWM, XLRE	1	2025-09-04 23:04:18.837873	2025-09-04 23:04:18.837873
3	Nasdaq100	AAPL, ABNB, ADBE, ADI, ADP, ADSK, AEP, AMAT, AMD, AMGN, AMZN, ANSS, ASML, AVGO, AXON, AZN, BIIB, BKNG, BKR, CCEP, CDNS, CDW, CEG, CHTR, CMCSA, COST, CPRT, CRWD, CSCO, CSGP, CSX, CTAS, CTSH, DASH, DDOG, DXCM, EA, EXC, FANG, FAST, FTNT, GFS, GILD, GOOGL, GOOGL, HON, IDXX, ILMN, INTC, INTU, ISRG, KDP, KHC, KLAC, LRCX, LULU, MAR, MCHP, MDB, MDLZ, MELI, META, MNST, MRNA, MRVL, MSFT, MU, NFLX, NXPI, ODFL, ON, ORLY, PANW, PAYX, PCAR, PDD, PEP, PYPL, QCOM, REGN, ROP, ROST, SBUX, SNPS, TEAM, TMUS, TSLA, TTD, TTWO, TXN, VRSK, VRTX, WBA, WBD, WDAY, XEL, ZS	1	2025-09-04 23:04:18.837873	2025-09-04 23:04:18.837873
5	Crypto	bito, ibit, mstr, coin, bmnr	1	2025-09-04 23:09:48.009883	2025-09-04 23:09:48.009883
6	Tech Stocks	AAPL,MSFT,GOOGL	1	2025-09-07 14:39:36.459759	2025-09-07 14:39:36.459759
7	S&P 500	SPY,QQQ,IWM	2	2025-09-07 14:39:36.459759	2025-09-07 14:39:36.459759
8	Admin Test	TSLA,NVDA,AMD	6	2025-09-07 14:39:36.459759	2025-09-07 14:39:36.459759
\.


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.users_id_seq', 6, true);


--
-- Name: watchlists_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.watchlists_id_seq', 8, true);


--
-- Name: admin_users admin_users_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_pkey PRIMARY KEY (user_id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: watchlists watchlists_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_pkey PRIMARY KEY (id);


--
-- Name: admin_users admin_users_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: watchlists watchlists_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: cloud_admin
--

ALTER DEFAULT PRIVILEGES FOR ROLE cloud_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO neon_superuser WITH GRANT OPTION;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: cloud_admin
--

ALTER DEFAULT PRIVILEGES FOR ROLE cloud_admin IN SCHEMA public GRANT ALL ON TABLES TO neon_superuser WITH GRANT OPTION;


--
-- PostgreSQL database dump complete
--

