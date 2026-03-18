#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import logging
import os
import sys

# Import the converter from the original script
from dflash_to_eee import DFlashConverter

class GuiLogHandler(logging.Handler):
    """Custom logging handler to redirect logs to a Tkinter ScrolledText widget."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state='normal')
        self.text_widget.insert(tk.END, msg + '\n')
        self.text_widget.configure(state='disabled')
        self.text_widget.see(tk.END)

class DFlashGui:
    def __init__(self, root):
        self.root = root
        self.root.title("FRM3 D-Flash to EEPROM Converter")
        self.root.geometry("700x550")

        # Set up UI elements
        self._setup_ui()

        # Set up logger
        self.logger = logging.getLogger("dflash_gui")
        self.logger.setLevel(logging.INFO)
        self.gui_handler = GuiLogHandler(self.log_area)
        self.gui_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        self.logger.addHandler(self.gui_handler)

    def _setup_ui(self):
        # Main container
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header = tk.Label(main_frame, text="BMW FRM3 Recovery Tool", font=("Arial", 16, "bold"))
        header.grid(row=0, column=0, columnspan=2, pady=(0, 20))

        # Input File
        tk.Label(main_frame, text="Input D-Flash File (.bin):", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky='w')
        self.input_entry = tk.Entry(main_frame, width=50)
        self.input_entry.grid(row=2, column=0, padx=(0, 10), pady=(0, 10), sticky='ew')
        tk.Button(main_frame, text="Browse...", command=self._browse_input).grid(row=2, column=1, pady=(0, 10))

        # Output File
        tk.Label(main_frame, text="Output EEPROM File (.bin):", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky='w')
        self.output_entry = tk.Entry(main_frame, width=50)
        self.output_entry.grid(row=4, column=0, padx=(0, 10), pady=(0, 10), sticky='ew')
        tk.Button(main_frame, text="Browse...", command=self._browse_output).grid(row=4, column=1, pady=(0, 10))

        # Convert Button
        self.convert_btn = tk.Button(main_frame, text="CONVERT NOW", command=self._convert, 
                                     bg="#FF9800", fg="black", highlightbackground="#FF9800",
                                     font=("Arial", 14, "bold"), pady=10)
        self.convert_btn.grid(row=5, column=0, columnspan=2, sticky='ew', pady=20)

        # Log Area
        tk.Label(main_frame, text="Results & Module Info:", font=("Arial", 10, "bold")).grid(row=6, column=0, sticky='w')
        self.log_area = scrolledtext.ScrolledText(main_frame, height=18, state='disabled', wrap=tk.WORD, font=("Courier", 12, "bold"))
        self.log_area.grid(row=7, column=0, columnspan=2, sticky='nsew')

        # Warning text
        warning_lbl = tk.Label(main_frame, text="Note: Write output to EEE partition only.", fg="red", font=("Arial", 9, "italic"))
        warning_lbl.grid(row=8, column=0, columnspan=2, pady=(10, 0))

        # Configure weights
        main_frame.rowconfigure(7, weight=1)
        main_frame.columnconfigure(0, weight=1)

    def _browse_input(self):
        filename = filedialog.askopenfilename(title="Select D-Flash Dump", 
                                              filetypes=[("Binary files", "*.bin"), ("All files", "*.*")])
        if filename:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, filename)
            # Auto-suggest output name if empty
            if not self.output_entry.get():
                base, ext = os.path.splitext(filename)
                self.output_entry.insert(0, base + "_eee.bin")

    def _browse_output(self):
        filename = filedialog.asksaveasfilename(title="Save EEPROM Image", 
                                                defaultextension=".bin",
                                                filetypes=[("Binary files", "*.bin"), ("All files", "*.*")])
        if filename:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filename)

    def _convert(self):
        input_file = self.input_entry.get()
        output_file = self.output_entry.get()

        if not input_file or not output_file:
            messagebox.showerror("Error", "Please select both input and output files.")
            return

        if not os.path.exists(input_file):
            messagebox.showerror("Error", f"Input file not found: {input_file}")
            return

        # Clear log area
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state='disabled')

        self.logger.info(f"Processing: {os.path.basename(input_file)}")
        
        try:
            converter = DFlashConverter(self.logger)
            converter.convert(input_file, output_file)
            self.logger.info("--- SUCCESS: EEPROM Image Created ---")
            messagebox.showinfo("Success", "Conversion finished! Module data extracted.")
        except Exception as e:
            self.logger.error(f"CRITICAL ERROR: {str(e)}")
            messagebox.showerror("Conversion Failed", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = DFlashGui(root)
    root.mainloop()
