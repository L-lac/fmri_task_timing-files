import os
import glob
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# Detects the Mac username automatically
mac_username = os.popen("whoami").read().strip()
base_directory = f"/Users/{mac_username}/Documents/Experiment_Data/data"

# Helper functions
def find_behavioral_files(beh_directory):
  recog_files = sorted(glob.glob(os.path.join(beh_directory, "*_ObjectScenePairTask_local_recog_final_*.csv")))
  recog_file = next((file for file in recog_files if not any(suffix in file for suffix in ["recogblocks", "recogrun", "recogtrial"])), None)

  study_files = sorted(glob.glob(os.path.join(beh_directory, "*_ObjectScenePairTask_local_study2_*.csv")))
  study_file = next((file for file in study_files if not any(suffix in file for suffix in ["studyblock", "studytrial", "runs"])), None)

  return recog_file, study_file if recog_file and study_file else (None, None)

def extract_material_type(row):
  if "object" in str(row).lower(): return "Object"
  elif "scene" in str(row).lower(): return "Scene"
  elif "pair" in str(row).lower(): return "Pair"
  else: return None

def determine_condition(row):
  if pd.isna(row['NewImg']): return None
  if row['NewImg'] == 'New': return 'New'
  if row['NewImg'] == 'Studied':
      if row['ConType'] == 1: return 'Old'
      if row['ConType'] > 1: return 'Lure'
  return None

def signal_detection(row):
  if row['Condition'] == 'Old':
      return 'Hit' if row['Recog1_Resp.corr'] == 1 else 'Miss'
  elif row['Condition'] in ['New', 'Lure']:
      return 'CR' if row['Recog1_Resp.corr'] == 1 else 'FA'
  else: return None

def material_attribute(row):
  if row['corrAns1'] == 'num_8':
      if row['Material_Type'] == 'Object': return 'Living'
      if row['Material_Type'] == 'Scene': return 'Indoor'
      if row['Material_Type'] == 'Pair': return 'Likely'
  elif row['corrAns1'] == 'num_5':
      if row['Material_Type'] == 'Object': return 'Nonliving'
      if row['Material_Type'] == 'Scene': return 'Outdoor'
      if row['Material_Type'] == 'Pair': return 'Unlikely'
  return None

def recognition_accuracy(run_data):
  run_data['Recog1_Resp.keys'] = run_data['Recog1_Resp.keys'].replace({1: 'num_8', 2: 'num_5'})
  run_data['Recog1_Resp.corr'] = (run_data['Recog1_Resp.keys'] == run_data['corrAns1']).astype(int)
  run_data.loc[run_data['Recog1_Resp.keys'].isna(), 'Recog1_Resp.corr'] = None
  return run_data

def extract_stimulus_start_time(imagefile, study_input_data):
  if pd.isna(imagefile): return None
  parts = imagefile.split("/")
  if len(parts) > 1:
      image_id = parts[-1].split("_")[0]
  else: return None
  matched_row = study_input_data[study_input_data['imagefile'].astype(str).str.contains(image_id, regex=False, na=False)]
  if not matched_row.empty:
      return matched_row['stimulus_start_time'].dropna().values[0] if 'stimulus_start_time' in study_input_data.columns else None
  return None

# 🌟 Main Loop
while True:
  selected_subjects = input("\nPlease Enter the Participant IDs you wish to process (separate with a comma) -> Ex: CBAS0001, CBAS0004: ").split(",")

  for subject in selected_subjects:
    subject = subject.strip()
    subject_path = os.path.join(base_directory, subject, "Time1")

    if not os.path.exists(subject_path):
      print(f"Skipping {subject} - No 'Time1' folder found at {subject_path}")
      continue

    # Updated path to mri_beh/memory/
    beh_folder = os.path.join(subject_path, "mri_beh", "memory")
    if not os.path.exists(beh_folder):
      print(f"Skipping {subject} - No 'mri_beh/memory' folder found at {beh_folder}")
      continue

    recog_file, study_file = find_behavioral_files(beh_folder)
    if not recog_file or not study_file:
      print(f"Skipping {subject} - Missing required input files in {beh_folder}")
      continue

    print(f"\nProcessing {subject} - Recognition: {recog_file}, Study: {study_file}")

    output_folder = os.path.join(beh_folder, "Memory_Task_Outputs")
    timing_folder = os.path.join(beh_folder, "Memory_Task_Timing_Files")
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(timing_folder, exist_ok=True)

    data = pd.read_csv(recog_file, encoding='utf-8-sig')
    study_input_data = pd.read_csv(study_file, encoding='utf-8-sig')
    study_input_data.columns = study_input_data.columns.str.strip().str.lower()

    data['stimulus_start_time'] = data['stimulus_start_time'].ffill()
    data['Run'] = 1
    current_run = 1
    for row in range(1, len(data)):
      if data['stimulus_start_time'].iloc[row] < data['stimulus_start_time'].iloc[row - 1]:
        current_run += 1
      data.loc[row, 'Run'] = current_run

      for run in data['Run'].unique():
        run_data = data[data['Run'] == run].copy()

        run_data['Condition'] = run_data.apply(determine_condition, axis=1)
        run_data['Material_Type'] = run_data['CondsFile'].apply(extract_material_type)
        run_data['Duration'] = run_data['stimulus_end_time'] - run_data['stimulus_start_time']
        run_data['Signal_Detection_Type'] = run_data.apply(signal_detection, axis=1)
        run_data['Material_Attribute'] = run_data.apply(material_attribute, axis=1)

        run_data.rename(columns={'stimulus_start_time': 'Onset_Time'}, inplace=True)
        run_data = recognition_accuracy(run_data)
        run_data.rename(columns={'Recog1_Resp.corr': 'Recognition_Accuracy'}, inplace=True)

        recognition_columns = ['Material_Type', 'NewImg', 'ImageFile', 'ConType', 'Condition', 'Recognition_Accuracy', 'Onset_Time', 'Duration', 'Signal_Detection_Type', 'Material_Attribute']

        study_data = run_data[run_data['NewImg'] == 'Studied'].copy()
        study_data['Duration'] = 3
        study_data.columns = study_data.columns.str.strip()
        study_data['stimulus_start_time'] = study_data['ImageFile'].apply(lambda img: extract_stimulus_start_time(img, study_input_data))

        study_columns = ['Material_Type', 'NewImg', 'ImageFile', 'stimulus_start_time', 'Duration', 'Condition', 'Recognition_Accuracy', 'Signal_Detection_Type', 'Material_Attribute']

        recog_file_name = os.path.join(output_folder, f"Run{int(run)}_Recognition.xlsx")
        wb_recog = Workbook()
        ws_recog = wb_recog.active
        ws_recog.title = "Recognition Phase"
        ws_recog.append(recognition_columns)
        for row in dataframe_to_rows(run_data[recognition_columns], index=False, header=False):
          ws_recog.append(row)
        wb_recog.save(recog_file_name)

        study_file_name = os.path.join(output_folder, f"Run{int(run)}_Study.xlsx")
        wb_study = Workbook()
        ws_study = wb_study.active
        ws_study.title = "Study Phase"
        ws_study.append(study_columns)
        for row in dataframe_to_rows(study_data[study_columns], index=False, header=False):
          ws_study.append(row)
        wb_study.save(study_file_name)

    print("The study and recognition phase outputs have been generated! 😊")

    runs = [1, 2, 3, 4]
    phases = ["Recognition", "Study"]
    material_types = {"Object": "Obj", "Scene": "Scn", "Pair": "Pair"}
    conditions = {
            "Hit": ["Hit"],
            "Miss": ["Miss"],
            "CR": ["CR"],
            "FA": ["FA"],
            "All_Correct": ["Hit", "CR"],
            "All_Wrong": ["Miss", "FA"],
        }

    for run in runs:
      for phase in phases:
        file_name = os.path.join(output_folder, f"Run{run}_{phase}.xlsx")
        if not os.path.exists(file_name):
          continue

        df = pd.read_excel(file_name)
        required_columns = {'Material_Type', 'Signal_Detection_Type', 'Duration'}
        if phase == "Study": required_columns.add('stimulus_start_time')
        else: required_columns.add('Onset_Time'
        if not required_columns.issubset(df.columns): 
          continue

        for material, short_name in material_types.items():
          material_df = df[df['Material_Type'] == material]
          for condition, condition_values in conditions.items():
            filtered_df = material_df[material_df['Signal_Detection_Type'].isin(condition_values)]

            timing_file = os.path.join(timing_folder, f"{phase}_Run{run}_{short_name}_{condition}.txt")
            with open(timing_file, "w") as f:
              if not filtered_df.empty:
                for _, row in filtered_df.iterrows():
                  onset_time = row['stimulus_start_time'] if phase == "Study" else row['Onset_Time']
                  f.write(f"{onset_time:.3f} {row['Duration']:.3f} 1\n")

      print("Timing files created! 🥳")
# After processing current batch
continue_processing = input("\nWould you like to process more participants? (yes/no): ").lower()
 if continue_processing not in ['yes', 'y']:
  print("\n All processing complete! Have a great day! 🎉")
  break
