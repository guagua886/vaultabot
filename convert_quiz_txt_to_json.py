import json
import re

INPUT_FILE = 'quiz_bank.txt'
OUTPUT_FILE = 'quiz_bank.json'

def parse_txt_to_quiz_list():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = [b.strip() for b in content.strip().split('\n\n') if b.strip()]
    quizzes = []

    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 6:
            continue
        question = lines[0].strip()
        options = lines[1:5]
        answer_line = lines[5].strip()

        match = re.search(r'答案[:：]([A-D])', answer_line)
        if not match:
            continue

        correct_letter = match.group(1).upper()
        correct_index = ord(correct_letter) - ord('A')
        options_cleaned = [line[2:].strip() if line[1] == '.' else line for line in options]

        quizzes.append({
            "question": question,
            "options": options_cleaned,
            "answer": correct_index
        })

    return quizzes

if __name__ == '__main__':
    quiz_data = parse_txt_to_quiz_list()
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(quiz_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 成功转换 {len(quiz_data)} 道题并写入 {OUTPUT_FILE}")

