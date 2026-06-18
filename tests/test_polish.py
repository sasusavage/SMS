"""Polish: guardian phone validation (warn, don't block) on CSV import."""
from services import notify, people
from tests.factories import make_school


def test_looks_like_valid_phone():
    f = notify.looks_like_valid_phone
    assert f('0244123456') is True
    assert f('+233244123456') is True
    assert f('') is True            # blank = optional, no opinion
    assert f(None) is True
    assert f('02011424183') is False   # the 11-digit typo
    assert f('123') is False


def test_csv_preview_warns_bad_guardian_phone(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    csv_text = (
        'admission_no,first_name,last_name,guardian_phone\n'
        'A1,Ama,Owusu,0244123456\n'       # valid
        'A2,Kofi,Mensah,02011424183\n'    # invalid (warn, still importable)
    )
    preview = people.parse_student_csv(s.id, csv_text)
    # both rows are VALID (importable) — phone is only a warning
    assert preview['valid'] == 2 and preview['invalid'] == 0
    row2 = preview['rows'][1]
    assert row2['errors'] == []
    assert any('may not be a valid Ghana number' in w for w in row2['warnings'])


def test_csv_preview_no_warning_for_blank_phone(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    csv_text = ('admission_no,first_name,last_name,guardian_phone\n'
                'A1,Ama,Owusu,\n')
    preview = people.parse_student_csv(s.id, csv_text)
    assert preview['rows'][0]['warnings'] == []
