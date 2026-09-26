from PIL import Image
from app.screenshots.mapper import OCRWord, extract_transcript_words, map_ocr_words, unique_ordered_matches


def words(*texts):
    return [OCRWord(text, 90.0, (i * 10, 0, 10, 10)) for i, text in enumerate(texts)]


def test_repeated_word_crop_is_not_arbitrarily_assigned():
    assert unique_ordered_matches(['the', 'cat', 'the', 'dog'], ['the']) == {}


def test_missing_repeated_word_keeps_both_occurrences_unknown():
    assert unique_ordered_matches(['go', 'go', 'home'], ['go', 'home']) == {2: 1}


def test_insertion_and_missing_word_do_not_shift_colors():
    result = map_ocr_words('The blue bird sings.', words('header', 'The', 'bird', 'sings.'),
                           Image.new('RGB', (50, 10), (20, 170, 50)), 'image-1')
    assert [t['candidate_color'] for t in result['tokens']] == ['green', 'unknown', 'green', 'green']
    assert result['tokens'][2]['ocr_text'] == 'bird'
    assert result['transcript_raw'] == 'The blue bird sings.'
    assert all(t['color'] == 'unknown' for t in result['tokens'])
    assert result['pause_status'] == 'unavailable'


def test_low_confidence_and_gray_pixels_stay_unknown():
    result = map_ocr_words('one two', [OCRWord('one', 10, (0, 0, 10, 10)), OCRWord('two', 95, (10, 0, 10, 10))],
                           Image.new('RGB', (20, 10), 'gray'), 'image-2')
    assert result['candidate_count'] == 0
    assert result['tokens'][0]['reason'] == 'low_ocr_confidence'
    assert result['tokens'][1]['reason'] == 'uncertain_color'


def test_context_disambiguates_repeated_tokens():
    assert unique_ordered_matches(['the', 'cat', 'the', 'dog'], ['the', 'cat', 'the', 'dog']) == dict(enumerate(range(4)))


def test_sparse_unrelated_matches_do_not_receive_color():
    result = map_ocr_words('a different full sentence', words('a'), Image.new('RGB', (10, 10), (200, 20, 30)), 'image-3')
    assert result['candidate_count'] == 0


def test_transcript_block_excludes_colored_header_and_footer():
    image = Image.new('RGB', (400, 350), 'white')
    words = [OCRWord('header', 90, (0, 0, 25, 10))]
    for row in range(3):
        for column, text in enumerate(('the', 'same', 'word', 'again')):
            words.append(OCRWord(text, 90, (column * 45, 100 + row * 35, 30, 12)))
    words.append(OCRWord('footer', 90, (0, 320, 25, 10)))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for word in words:
        draw.rectangle((word.bbox[0], word.bbox[1], word.bbox[0] + word.bbox[2], word.bbox[1] + word.bbox[3]), fill=(200, 20, 30))
    extracted = extract_transcript_words(words, image)
    assert [word.text for word in extracted] == ['the', 'same', 'word', 'again'] * 3
