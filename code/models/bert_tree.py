from transformers import AutoTokenizer, AutoConfig, TFAutoModel, DataCollatorWithPadding
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, GradientBoostingClassifier
import numpy as np
import pickle

from models.bert import BERT
from evaluation import evaluate
from utils import set_seeds

bert_params = {
    'model': 'emilyalsentzer/Bio_ClinicalBERT',
    'learning_rate': 0.0003,
    'batch_size': 1,
    'epochs': 4,
    'dataset': 'small',
    'freeze_base_layer': True,
    'load_checkpoint': False,
    'save_checkpoints': False,
    'load_cached_dataset': True,
    'save_results': True
}


class BERTTree:

    def __init__(self, params):
        self.params = params

        model = self.params['model']
        self.tokenizer = AutoTokenizer.from_pretrained(model)
        config = AutoConfig.from_pretrained(model)
        self.model = TFAutoModel.from_pretrained(model,
                                                 config=config,
                                                 from_pt=True)

    def load_data(self):
        bert = BERT(bert_params)
        bert.load_data()
        self.tokenized_dataset = bert.dataset.map(
            lambda sample: self.tokenizer(sample['text'],
                                          truncation=True,
                                          padding='max_length',
                                          max_length=100))
        data_collator = DataCollatorWithPadding(tokenizer=self.tokenizer,
                                                return_tensors='tf')

        #train = self.tokenized_dataset['train'].to_tf_dataset(
        #    columns=['attention_mask', 'input_ids', 'token_type_ids'],
        #    label_cols=['label'],
        #    shuffle=False,
        #    collate_fn=data_collator,
        #    batch_size=32,
        #)

        #test = self.tokenized_dataset['test'].to_tf_dataset(
        #    columns=['attention_mask', 'input_ids', 'token_type_ids'],
        #    label_cols=['label'],
        #    shuffle=False,
        #    collate_fn=data_collator,
        #    batch_size=32,
        #)

        #self.tf_dataset = {
        #    'train': train,
        #    'test': test,
        #}

    def compute_features(self, dataset):
        print('computing features...')
        SHARDS = 10
        Xs = []
        for i in range(SHARDS):
            dataset_shard = self.tokenized_dataset[dataset].shard(
                num_shards=SHARDS, index=i)
            data_collator = DataCollatorWithPadding(tokenizer=self.tokenizer,
                                                    return_tensors='tf')
            tf_shard = dataset_shard.to_tf_dataset(
                columns=['attention_mask', 'input_ids', 'token_type_ids'],
                label_cols=['label'],
                shuffle=False,
                collate_fn=data_collator,
                batch_size=32,
            )

            bert_output = self.model.predict(tf_shard, verbose=1)[0]
            X = bert_output.reshape(bert_output.shape[0], -1)
            Xs.append(X)

        X = np.concatenate(Xs)
        y = np.array(self.tokenized_dataset[dataset]['label'])

        return X, y

    def generate_features(self, dataset):
        X, y = self.compute_features(dataset)

        model_name = bert_params['model'].split('/')[-1]
        identifier = f'{dataset}_{bert_params["dataset"]}_{model_name}'

        with open(os.path.join('data', f'X_feat_{identifier}.pkl'), 'wb') as f:
            pickle.dump(X, f)

        with open(os.path.join('data', f'y_{identifier}.pkl'), 'wb') as f:
            pickle.dump(y, f)

    def train(self):
        # Load from cache if exists
        identifier = f'{bert_params["dataset"]}_{model_name}'
        if f'X_feat_train_{identifier}.pkl' in os.listdir('data'):
            with open(os.path.join('data', f'X_feat_train_{identifier}.pkl'),
                      'rb') as f:
                X_train = pickle.load(f)
            with open(os.path.join('data', f'y_train_{identifier}.pkl'),
                      'rb') as f:
                y_train = pickle.load(f)
        else:
            X_train, y_train = self.compute_features('train')

        for clf in self.params['classifiers']:
            print('training', str(clf))
            clf.fit(X_train, y_train)

    def evaluate(self):
        X_test, y_test = self.compute_features('test')
        for clf in self.params['classifiers']:
            y_pred = clf.predict_proba(X_test)
            evaluate(str(clf), y_pred, y_test, save_results=True)


if __name__ == '__main__':
    set_seeds()

    params = {
        'model':
            'emilyalsentzer/Bio_ClinicalBERT',
        'classifiers': [
            ExtraTreesClassifier(n_estimators=100, random_state=0, verbose=1),
            RandomForestClassifier(n_estimators=100, random_state=0, verbose=1),
            GradientBoostingClassifier(n_estimators=100,
                                       random_state=0,
                                       verbose=1)
        ],
    }

    bert_tree = BERTTree(params)
    bert_tree.load_data()
    bert_tree.generate_features('train')
    bert_tree.generate_features('test')
    #bert_tree.train()
    #bert_tree.evaluate()
