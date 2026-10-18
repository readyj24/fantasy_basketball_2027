from draftboard.ingest import load_projections, load_ranking


def test_hashtag_paste(tmp_path):
    # Hashtag's table copies as tab-separated with made/attempts in the % cells
    # and repeated header rows.
    p = tmp_path / "proj.tsv"
    p.write_text(
        "R#\tPLAYER\tPOS\tTEAM\tGP\tMPG\tFG%\tFT%\t3PM\tPTS\tTREB\tAST\tSTL\tBLK\tTO\tTOTAL\n"
        "1\tNikola Jokić\tC\tDEN\t72\t35.1\t0.578 (10.6/18.3)\t0.810 (5.2/6.4)\t1.3\t27.6\t12.4\t9.8\t1.5\t0.7\t3.1\t12.1\n"
        "R#\tPLAYER\tPOS\tTEAM\tGP\tMPG\tFG%\tFT%\t3PM\tPTS\tTREB\tAST\tSTL\tBLK\tTO\tTOTAL\n"
        "2\tShai Gilgeous-Alexander\tPG,SG\tOKC\t74\t34.0\t0.530 (10.9/20.6)\t0.890 (7.9/8.9)\t1.9\t31.5\t5.2\t6.1\t2.0\t0.9\t2.4\t11.0\n",
        encoding="utf-8")
    df = load_projections(p)
    assert len(df) == 2
    assert df.loc[0, "fgm"] == 10.6 and df.loc[0, "fga"] == 18.3
    assert df.loc[1, "fta"] == 8.9 and df.loc[1, "yahoo_positions"] == "G"
    assert df.loc[0, "tov"] == 3.1 and df.loc[0, "reb"] == 12.4


def test_fantasypros_adp(tmp_path):
    p = tmp_path / "adp.csv"
    p.write_text('Rank,"Player Team (Position)",Yahoo,ESPN,AVG\n'
                 '1,"Nikola Jokic (DEN - C)",1.0,1.0,1.0\n'
                 '2,"Shai Gilgeous-Alexander (OKC - PG,SG)",2.3,2.0,2.1\n')
    t = load_ranking(p, "adp")
    assert t["value"].tolist() == [1.0, 2.3]


def test_yahoo_rank_names_only(tmp_path):
    p = tmp_path / "yr.csv"
    p.write_text("Player\nNikola Jokic\nVictor Wembanyama\n")
    t = load_ranking(p, "rank")
    assert t["value"].tolist() == [1, 2]
