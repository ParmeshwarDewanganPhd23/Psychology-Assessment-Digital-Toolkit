import os
import re
import time
import tkinter as tk
from copy import deepcopy
from datetime import datetime
from tkinter import ttk, messagebox

import pandas as pd

from utils import load_json, ensure_folder
from scorer import calculate_scores


class AssessmentApp:
    def __init__(self, root, config):
        self.root = root
        self.config = config

        self.responses = {}
        self.question_labels = {}
        self.questionnaires = []
        self.question_order = []
        self.submit_buttons = {}
        self.condition_fields = {}
        self.submitted_questionnaires = set()

        self.question_start_times = {}
        self.response_times = {}
        self.qid_to_prefix = {}
        self.tab_frames = {}
        self.tab_start_times = {}
        self.last_action_times = {}

        self.session_start = time.time()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        app_conf = config.get("app", {})
        root.title(app_conf.get("title", "Assessment Toolkit"))
        root.geometry(
            f"{app_conf.get('window_width', 1600)}x{app_conf.get('window_height', 950)}"
        )

        self.output_dir = app_conf.get("output_folder", "output")
        ensure_folder(self.output_dir)

        fonts = config.get("fonts", {})
        family = fonts.get("family", "Arial")
        self.question_font = (family, fonts.get("question_size", 12))
        self.option_font = (family, fonts.get("option_size", 10))
        self.instruction_font = (family, fonts.get("instruction_size", 12))

        self.build_top_bar()
        self.load_questionnaires()
        self.build_tabs()

    def build_top_bar(self):
        frame = ttk.Frame(self.root)
        frame.pack(pady=10, padx=10, fill="x")

        ttk.Label(frame, text="Subject ID").grid(row=0, column=0, sticky="w", padx=5)
        self.sid = ttk.Entry(frame, width=20)
        self.sid.grid(row=0, column=1, padx=10, sticky="w")

        ttk.Label(frame, text="Date").grid(row=0, column=2, sticky="w", padx=5)
        self.date = ttk.Entry(frame, width=15)
        self.date.insert(0, datetime.now().strftime("%d-%b-%Y"))
        self.date.grid(row=0, column=3, padx=10, sticky="w")

    def load_questionnaires(self):
        for item in self.config.get("questionnaires", []):
            path = os.path.join("questionnaires", f"{item['file']}.json")
            qdata = load_json(path)

            has_options = any("options" in q for q in qdata.get("questions", []))
            qdata["type"] = "multi_statement" if has_options else "likert"

            if "type" in item:
                qdata["type"] = item["type"]

            qdata["display"] = item.get("display", "horizontal")
            qdata["_prefix"] = item.get("id", qdata.get("name", "Q"))
            qdata["_display_name"] = item.get("name", qdata.get("name", "Questionnaire"))
            qdata["_has_condition"] = item.get("has_condition", False)

            self.questionnaires.append(qdata)

    def build_tabs(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)

        for qdata in self.questionnaires:
            self.build_questionnaire_tab(qdata)

        self.nb.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.after(100, self.initialize_first_tab_timer)

        for page in self.config.get("credits", []):
            path = os.path.join("credits", f"{page}.json")
            if os.path.exists(path):
                data = load_json(path)
                frame = ttk.Frame(self.nb)
                self.nb.add(frame, text=data.get("title", "Credits"))
                text = "\n".join(data.get("content", []))
                ttk.Label(
                    frame,
                    text=text,
                    wraplength=900,
                    justify="left",
                    font=self.instruction_font
                ).pack(padx=20, pady=20)

    def initialize_first_tab_timer(self):
        selected = self.nb.select()
        prefix = self.tab_frames.get(selected)
        if prefix and prefix not in self.tab_start_times:
            now = time.time()
            self.tab_start_times[prefix] = now
            self.last_action_times[prefix] = now

    def on_tab_changed(self, event=None):
        selected = self.nb.select()
        prefix = self.tab_frames.get(selected)
        if prefix and prefix not in self.tab_start_times:
            now = time.time()
            self.tab_start_times[prefix] = now
            self.last_action_times[prefix] = now

    def bind_mousewheel(self, canvas):
        def _on_mousewheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind)
        canvas.bind("<Leave>", _unbind)

    def build_questionnaire_tab(self, qdata):
        frame = ttk.Frame(self.nb)

        qname = qdata.get("_display_name", qdata.get("name", "Questionnaire"))
        prefix = qdata.get("_prefix", qname)
        has_condition = qdata.get("_has_condition", False)

        self.nb.add(frame, text=qname)
        self.tab_frames[str(frame)] = prefix

        if "instructions" in qdata:
            ttk.Label(
                frame,
                text=qdata["instructions"],
                wraplength=1100,
                font=self.instruction_font,
                justify="left"
            ).pack(pady=(10, 5), padx=10, anchor="w")

        if has_condition:
            cond_frame = ttk.Frame(frame)
            cond_frame.pack(pady=(0, 5), padx=10, anchor="w")

            ttk.Label(cond_frame, text="Condition").grid(
                row=0, column=0, sticky="w", padx=5
            )
            cond_entry = ttk.Entry(cond_frame, width=20)
            cond_entry.grid(row=0, column=1, sticky="w", padx=5)
            self.condition_fields[prefix] = cond_entry

        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(side="bottom", fill="x", pady=10)

        scroll_container = ttk.Frame(frame)
        scroll_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_container)
        scrollbar = ttk.Scrollbar(
            scroll_container, orient="vertical", command=canvas.yview
        )
        form = ttk.Frame(canvas)

        form.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.bind_mousewheel(canvas)

        display = qdata.get("display", "horizontal")
        row_pointer = 0

        for qnum, q in enumerate(qdata.get("questions", []), start=1):
            base_text = q.get("text") or q.get("label", "")
            label_text = f"{qnum}. {base_text}"

            label_widget = tk.Label(
                form,
                text=label_text,
                font=self.question_font,
                wraplength=1100,
                justify="left",
                bg="white",
                anchor="w"
            )
            label_widget.grid(
                row=row_pointer,
                column=0,
                sticky="w",
                pady=(10, 4),
                padx=10
            )

            qid = f"{prefix}_{q.get('id', '')}"
            var = tk.StringVar(value="")

            self.responses[qid] = var
            self.question_labels[qid] = label_widget
            self.question_start_times[qid] = time.time()
            self.qid_to_prefix[qid] = prefix

            self.question_order.append({
                "qid": qid,
                "qnum": qnum,
                "qname": qname,
                "prefix": prefix
            })

            var.trace_add("write", lambda *args, qid=qid: self.on_answer(qid))

            options_frame = ttk.Frame(form)
            options_frame.grid(
                row=row_pointer + 1,
                column=0,
                sticky="w",
                padx=25,
                pady=(0, 8)
            )

            if "options" in q:
                for opt in q["options"]:
                    label_opt = f"{opt.get('score')} : {opt.get('text', '')}"

                    if display == "horizontal":
                        tk.Radiobutton(
                            options_frame,
                            text=label_opt,
                            variable=var,
                            value=str(opt.get("score")),
                            font=self.option_font,
                            wraplength=250,
                            justify="left",
                            anchor="w"
                        ).pack(side="left", padx=8)
                    else:
                        tk.Radiobutton(
                            options_frame,
                            text=label_opt,
                            variable=var,
                            value=str(opt.get("score")),
                            font=self.option_font,
                            wraplength=700,
                            justify="left",
                            anchor="w"
                        ).pack(anchor="w")
            else:
                scale = q.get("scale", qdata.get("scale", [1, 2, 3, 4, 5]))

                for val in scale:
                    if isinstance(val, dict):
                        value = val.get("value")
                        label = val.get("label", "")
                        label_val = label if label else str(value)
                    else:
                        value = val
                        if isinstance(value, (int, float)) and 0 <= value <= 100:
                            label_val = f"{value}%"
                        else:
                            label_val = str(value)

                    if display == "horizontal":
                        tk.Radiobutton(
                            options_frame,
                            text=label_val,
                            variable=var,
                            value=str(value),
                            font=self.option_font,
                            anchor="w",
                            justify="left"
                        ).pack(side="left", padx=8)
                    else:
                        tk.Radiobutton(
                            options_frame,
                            text=label_val,
                            variable=var,
                            value=str(value),
                            font=self.option_font,
                            anchor="w"
                        ).pack(anchor="w")

            row_pointer += 2

        submit_btn = ttk.Button(
            bottom_frame,
            text=f"Submit {qname}",
            command=lambda q=qdata: self.submit_questionnaire(q)
        )
        submit_btn.pack()

        self.submit_buttons[prefix] = submit_btn

    def highlight_question(self, qid, color="#ccffcc"):
        label_widget = self.question_labels.get(qid)
        if label_widget:
            label_widget.configure(bg=color)

    def on_answer(self, qid):
        self.highlight_question(qid, color="#ccffcc")

        if qid not in self.response_times:
            now = time.time()
            prefix = self.qid_to_prefix.get(qid)

            if prefix not in self.tab_start_times:
                self.tab_start_times[prefix] = now
                self.last_action_times[prefix] = now

            base_time = self.last_action_times.get(prefix, self.tab_start_times[prefix])
            self.response_times[qid] = round(now - base_time, 2)
            self.last_action_times[prefix] = now

    def get_question_qids(self, qdata):
        prefix = qdata.get("_prefix", qdata.get("name", "Q"))
        qids = []

        for q in qdata.get("questions", []):
            qids.append(f"{prefix}_{q.get('id', '')}")

        return qids

    def validate_questionnaire(self, qdata):
        qname = qdata.get("_display_name", qdata.get("name", "Questionnaire"))
        prefix = qdata.get("_prefix", qname)
        missing = []

        for item in self.question_order:
            if item["prefix"] != prefix:
                continue

            qid = item["qid"]
            value = self.responses[qid].get().strip()

            if value == "":
                missing.append(item)
                self.highlight_question(qid, color="#ffdddd")

        if missing:
            preview = ", ".join([f"Q{item['qnum']}" for item in missing[:10]])
            extra = f" and {len(missing) - 10} more" if len(missing) > 10 else ""

            messagebox.showwarning(
                "Missing answers",
                f"Please answer all questions in {qname} before submitting.\n\nMissing: {preview}{extra}"
            )
            return False

        return True

    def sanitize_name(self, name):
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
        return safe or "questionnaire"

    def normalize_date_for_save(self):
        raw = self.date.get().strip()

        date_formats = [
            "%d-%b-%Y",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y/%m/%d"
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(raw, fmt).strftime("%d-%b-%Y")
            except ValueError:
                pass

        return raw if raw else datetime.now().strftime("%d-%b-%Y")

    def get_condition_value(self, qdata):
        prefix = qdata.get("_prefix", qdata.get("name", "Q"))
        has_condition = qdata.get("_has_condition", False)

        if not has_condition:
            return "NA"

        cond_entry = self.condition_fields.get(prefix)
        if cond_entry is None:
            return "NA"

        value = cond_entry.get().strip()
        return value if value else "NA"

    def submit_questionnaire(self, qdata):
        qname = qdata.get("_display_name", qdata.get("name", "Questionnaire"))
        prefix = qdata.get("_prefix", qname)
        has_condition = qdata.get("_has_condition", False)

        if prefix in self.submitted_questionnaires:
            messagebox.showinfo("Already saved", f"{qname} has already been saved.")
            return

        if not self.sid.get().strip():
            messagebox.showwarning("Missing", "Please enter Subject ID")
            return

        if not self.date.get().strip():
            messagebox.showwarning("Missing", "Please enter Date")
            return

        if has_condition:
            cond_entry = self.condition_fields.get(prefix)
            if cond_entry is None or not cond_entry.get().strip():
                messagebox.showwarning(
                    "Missing",
                    "Please enter Condition for this embodiment questionnaire."
                )
                return

        if not self.validate_questionnaire(qdata):
            return

        self.save_questionnaire_responses(qdata, status="submitted")
        self.submitted_questionnaires.add(prefix)

        if prefix in self.submit_buttons:
            self.submit_buttons[prefix].configure(
                text=f"{qname} Saved",
                state="disabled"
            )

        messagebox.showinfo("Saved", f"{qname} saved successfully.")

    def save_questionnaire_responses(self, qdata, status="submitted"):
        end_time = time.time()
        duration = round(end_time - self.session_start, 2)

        sid = self.sid.get().strip() or "UNKNOWN"
        date_value = self.normalize_date_for_save()
        qname = qdata.get("_display_name", qdata.get("name", "Questionnaire"))
        prefix = qdata.get("_prefix", qname)
        condition = self.get_condition_value(qdata)

        safe_prefix = self.sanitize_name(prefix)
        qids = self.get_question_qids(qdata)
        responses_dict = {qid: self.responses[qid].get() for qid in qids}

        participant_folder = os.path.join(self.output_dir, sid)
        os.makedirs(participant_folder, exist_ok=True)

        scoring_qdata = deepcopy(qdata)
        scoring_qdata["name"] = prefix

        scores_result = calculate_scores([scoring_qdata], responses_dict)

        all_data = []
        if isinstance(scores_result, dict) and "items" in scores_result:
            for qid, val_dict in scores_result["items"].items():
                all_data.append({
                    "SubjectID": sid,
                    "Condition": condition,
                    "Date": date_value,
                    "Questionnaire": qname,
                    "QuestionnaireID": prefix,
                    "Question": qid,
                    "Raw": val_dict.get("raw"),
                    "ReverseCoded": val_dict.get("score"),
                    "ResponseTime_sec": self.response_times.get(qid),
                    "Status": status,
                    "TotalDuration_sec": duration
                })
        else:
            for qid, raw in responses_dict.items():
                all_data.append({
                    "SubjectID": sid,
                    "Condition": condition,
                    "Date": date_value,
                    "Questionnaire": qname,
                    "QuestionnaireID": prefix,
                    "Question": qid,
                    "Raw": raw,
                    "ReverseCoded": raw,
                    "ResponseTime_sec": self.response_times.get(qid),
                    "Status": status,
                    "TotalDuration_sec": duration
                })

        all_df = pd.DataFrame(all_data)
        all_df.to_csv(
            os.path.join(participant_folder, f"{safe_prefix}_all_questions.csv"),
            index=False
        )

        total_row = {
            "SubjectID": sid,
            "Condition": condition,
            "Date": date_value,
            "Questionnaire": qname,
            "QuestionnaireID": prefix,
            "Duration_sec": duration,
            "Status": status
        }

        if isinstance(scores_result, dict) and "totals" in scores_result:
            total_row.update(scores_result["totals"])
        else:
            total_row.update(scores_result)

        total_df = pd.DataFrame([total_row])
        total_df.to_csv(
            os.path.join(participant_folder, f"{safe_prefix}_total.csv"),
            index=False
        )

        master_file = os.path.join(self.output_dir, f"Master_scores_{safe_prefix}.csv")
        if os.path.exists(master_file):
            total_df.to_csv(master_file, mode="a", header=False, index=False)
        else:
            total_df.to_csv(master_file, index=False)

    def on_close(self):
        unsaved = []

        for qdata in self.questionnaires:
            prefix = qdata.get("_prefix", qdata.get("name", "Q"))
            qname = qdata.get("_display_name", qdata.get("name", "Questionnaire"))

            if prefix not in self.submitted_questionnaires:
                unsaved.append(qname)

        if unsaved:
            msg = (
                "The following questionnaires are not submitted yet:\n\n- "
                + "\n- ".join(unsaved)
                + "\n\nExit without saving them?"
            )
        else:
            msg = "Exit application?"

        if messagebox.askyesno("Exit", msg):
            self.root.destroy()